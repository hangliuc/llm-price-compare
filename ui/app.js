const { createApp, ref, computed, onMounted, onBeforeUnmount, nextTick, watch } = Vue;

const USD_TO_CNY = 7.2;  // MVP 硬编码汇率

// 首页价格预览只展示模型原厂的旗舰系列。规则按优先级排列：同一厂商
// 命中多个系列时先选更旗舰的系列，再在该系列中选择发布时间最新的模型。
const HOME_FLAGSHIP_PROVIDER_RULES = [
  { providerId: 'openai', modelPatterns: [/^GPT-\d+(?:\.\d+)? Sol$/i, /^GPT-\d+(?:\.\d+)?$/i] },
  { providerId: 'anthropic', modelPatterns: [/^Claude Opus\b/i] },
  { providerId: 'google', modelPatterns: [/^Gemini\b.*\bPro\b/i] },
  { providerId: 'qwen', modelPatterns: [/^Qwen.*\bMax\b/i] },
  { providerId: 'deepseek', modelPatterns: [/^DeepSeek\b.*\bPro\b/i, /^DeepSeek(?!.*\bFlash\b)/i] },
  { providerId: 'moonshot', modelPatterns: [/^Kimi K\d+(?:\.\d+)?$/i] },
  { providerId: 'zhipu', modelPatterns: [/^GLM-\d+(?:\.\d+)?$/i] },
  { providerId: 'minimax', modelPatterns: [/^MiniMax-M\d+(?:\.\d+)?$/i] },
];

// Production Nginx exposes the V3 catalog at /data/catalog.json. A repository-
// root Python server can read the same artifact directly from runtime/.
const DATA_PATHS = ["../data/catalog.json"];
if (['localhost', '127.0.0.1'].includes(window.location.hostname)) {
  DATA_PATHS.push("../runtime/public/catalog.json");
}

// V3 separates model offers and plans. Existing views consume provider-grouped
// rows, so adapt once at the network boundary.
function catalogV3ToViewData(catalog) {
  if (!catalog || catalog.schema_version !== '3.0') return catalog;
  const providerMap = new Map((catalog.providers || []).map(provider => [provider.id, {
    ...provider,
    products: [],
  }]));
  const ensureProvider = (providerId, providerName) => {
    if (!providerMap.has(providerId)) {
      providerMap.set(providerId, {
        id: providerId, name: providerName || providerId, name_en: providerName || providerId,
        region: 'unknown', website: '', products: [],
      });
    }
    return providerMap.get(providerId);
  };
  for (const item of catalog.model_offers || []) {
    ensureProvider(item.provider_id, item.provider_name).products.push({
      id: item.offer_id,
      canonical_id: item.model_id,
      model: item.model_name,
      billing_type: 'per_token',
      context_window: item.context_window ?? null,
      modalities: item.modalities || [],
      release_date: item.release_date || null,
      prices: {
        input: item.input_per_1m,
        output: item.output_per_1m,
        cached_input: item.cache_read_per_1m,
        cache_write: item.cache_write_per_1m,
        currency: item.currency,
      },
      purchase_url: item.source_url || '',
      notes: null,
      plan_category: null,
      featured_on_home: false,
      data_status: 'accepted',
      stale_fields: [],
    });
  }
  for (const item of catalog.plans || []) {
    ensureProvider(item.provider_id, item.provider_name).products.push({
      id: item.plan_id,
      canonical_id: item.plan_id,
      model: item.product_name,
      billing_type: item.billing_type,
      context_window: null,
      modalities: [],
      release_date: null,
      prices: {
        monthly_price: item.monthly_equivalent ?? item.price_amount,
        first_month_price: item.first_period_price,
        included_quota: item.included_quota,
        quota_unit: item.quota_unit,
        quota_period: item.quota_period,
        features: item.features || [],
        currency: item.currency,
      },
      purchase_url: item.purchase_url || item.source_url || '',
      notes: null,
      plan_category: item.plan_category || null,
      featured_on_home: Boolean(item.featured_on_home),
      data_status: 'accepted',
      stale_fields: [],
    });
  }
  const providers = [...providerMap.values()].filter(provider => provider.products.length);
  return {
    generated_at: catalog.published_at,
    release_id: catalog.release_id,
    schema_version: catalog.schema_version,
    providers,
    provider_status: providers.map(provider => ({
      provider_id: provider.id,
      stale: false,
      last_success_at: catalog.published_at,
    })),
  };
}

// 厂商图标路径（/ui/ 下用相对路径，根路径用 ui/icons/）
// 图标文件名映射（厂商 id → 实际文件名，不含扩展名）
const ICON_FILES = {
  openai: 'openai-black',
  anthropic: 'Anthropic',
  zhipu: 'zhipu',
  volcengine: 'volcengine',
  deepseek: 'deepseek',
  opencode: 'icon-opencode',
  google: 'google',
  qwen: 'qwen',
  moonshot: 'kimi',
  aws: 'aws',
  minimax: 'minimax',
  xiaomi: '小米',
  githubcopilot: 'githubcopilot',
  cursor: 'cursor',
  kiro: 'kiro',
};
const PNG_ICONS = ['volcengine'];
const iconUrl = (id) => {
  if (!id) return 'icons/ppx.svg';
  const name = ICON_FILES[id] || id;
  const ext = PNG_ICONS.includes(id) ? 'png' : 'svg';
  // <base href="/ui/"> 已让相对路径基于 /ui/，统一用 icons/相对路径
  return `icons/${name}.${ext}`;
};

// 厂商品牌色（图标加载失败时用作占位背景）
const PROVIDER_COLORS = {
  openai: '#10A37F', anthropic: '#191919', zhipu: '#4B6BFF', volcengine: '#0B8CE6',
  deepseek: '#5786FE', opencode: '#1a1a1a', google: '#4285F4',
  qwen: '#6950EF', moonshot: '#000000',
  aws: '#FF9900', minimax: '#FF6B6B', xiaomi: '#FF6900',
  githubcopilot: '#24292E', cursor: '#000000',
  kiro: '#FF9900',
};

// 厂商元数据（用于 provider_status 中存在但 providers 数组中没有的抓取失败厂商）
const PROVIDER_META = {
  openai: { name: 'OpenAI', name_en: 'OpenAI', region: 'us' },
  anthropic: { name: 'Anthropic', name_en: 'Anthropic', region: 'us' },
  zhipu: { name: '智谱', name_en: 'Zhipu', region: 'cn' },
  volcengine: { name: '火山引擎', name_en: 'Volcengine', region: 'cn' },
  deepseek: { name: 'DeepSeek', name_en: 'DeepSeek', region: 'cn' },
  opencode: { name: 'OpenCode', name_en: 'OpenCode', region: 'cn' },
  google: { name: 'Google', name_en: 'Google', region: 'us' },
  qwen: { name: '阿里通义', name_en: 'Alibaba Qwen', region: 'cn' },
  moonshot: { name: 'Kimi', name_en: 'Moonshot AI', region: 'cn' },
  aws: { name: 'AWS', name_en: 'Amazon Web Services', region: 'us' },
  minimax: { name: 'MiniMax', name_en: 'MiniMax', region: 'cn' },
  xiaomi: { name: '小米', name_en: 'Xiaomi', region: 'cn' },
  githubcopilot: { name: 'GitHub Copilot', name_en: 'GitHub Copilot', region: 'us' },
  cursor: { name: 'Cursor', name_en: 'Cursor', region: 'us' },
  kiro: { name: 'Kiro', name_en: 'Kiro', region: 'us' },
};

// Hero 轨道只展示模型 / 云 / API 厂商。开发工具由首页 AI Coding IDE 专区承载。
const CODING_TOOL_PROVIDER_IDS = new Set(['cursor', 'kiro', 'githubcopilot', 'opencode']);

// AI Coding IDE 生态：独立于价格库，便于后续增删产品而不改模板。
const CODING_IDES = [
  { id: 'cursor', name: 'Cursor', logo: 'icons/cursor.svg', url: 'https://www.cursor.com/', category: 'AI 原生 IDE', description: '面向 AI 编程工作流的代码编辑器' },
  { id: 'trae', name: 'Trae', logo: 'icons/trae.png', url: 'https://www.trae.ai/', category: 'AI 原生 IDE', description: '以 Agent 为核心的开发环境' },
  { id: 'windsurf', name: 'Windsurf', logo: 'icons/windsurf.png', url: 'https://windsurf.com/', category: 'Agentic IDE', description: '编辑器与编码 Agent 协同工作' },
  { id: 'qoder', name: 'Qoder', logo: 'icons/qoder.png', url: 'https://qoder.com/', category: 'Agentic IDE', description: '面向真实软件任务的智能开发平台' },
  { id: 'kiro', name: 'Kiro', logo: 'icons/kiro.svg', url: 'https://kiro.dev/', category: 'Agentic IDE', description: '从规格到交付的 Agentic 开发环境' },
  { id: 'zed', name: 'Zed', logo: 'icons/zed.png', url: 'https://zed.dev/ai', category: 'AI 增强编辑器', description: '原生集成 Agent 的高性能编辑器' },
  { id: 'antigravity', name: 'Antigravity', logo: 'icons/antigravity.png', url: 'https://antigravity.google/', category: 'Agentic IDE', description: 'Google 的 Agent-first 开发平台' },
  { id: 'replit', name: 'Replit', logo: 'icons/replit.png', url: 'https://replit.com/', category: '云端 AI IDE', description: '从想法到部署的一体化云开发环境' },
  { id: 'vscode', name: 'VS Code', logo: 'icons/vscode.png', url: 'https://code.visualstudio.com/docs/agents/overview', category: 'AI 增强编辑器', description: '内置多种编码 Agent 工作流' },
  { id: 'jetbrains', name: 'JetBrains + Junie', logo: 'icons/jetbrains.svg', url: 'https://www.jetbrains.com/junie/', category: 'AI 增强 IDE', description: 'JetBrains IDE 内的自主编码 Agent' },
];
const CODING_IDE_ROWS = [CODING_IDES.slice(0, 5), CODING_IDES.slice(5)];

createApp({
  setup() {
    const data = ref(null);
    const error = ref(null);
    const searchQuery = ref("");
    // 全局导航搜索（首页/比较页共用）：输入厂商中英文名/ID 模糊匹配，下拉建议跳转
    const globalSearch = ref("");
    const searchFocused = ref(false);
    const plansMenuOpen = ref(false);
    const homePlansMenuOpen = ref(false);
    // 视图模式：coding_plan/subscription 默认卡片，其它默认表格
    // _viewOverride 记录用户手动切换后的值，避免路由变化时覆盖
    const _viewOverride = ref(null);
    const view = computed({
      get() {
        if (_viewOverride.value) return _viewOverride.value;
        // coding_plan/subscription 路由默认卡片
        if (billingRoute.value === 'coding_plan' || billingRoute.value === 'subscription') {
          return 'card';
        }
        return 'table';
      },
      set(v) { _viewOverride.value = v; },
    });
    const displayCurrency = ref("CNY");
    // 厂商详情页：当前选中的计费方式 tab（per_token / subscription / coding_plan）
    const providerBillingTab = ref(null);
    const expanded = ref(null);
    const sortKey = ref("release_date");
    const sortAsc = ref(false);
    const route = ref(window.location.hash || "#/");
    const filters = ref({
      region: [],
      billing: [],
      modality: [],
      provider: [],
    });
    // Compare 页面独立交互状态：只面向按需计费模型，不影响计费类型页面。
    const compareContextFilter = ref('');
    const compareSearchQuery = ref('');
    const comparePriceFilter = ref('');
    const compareRegionFilter = ref('');
    const compareProviderFilters = ref([]);
    const compareModalityFilters = ref([]);
    const compareSortOption = ref('release_date:desc');
    const compareVisibleFields = ref(['input', 'output', 'cached_input', 'context_window']);
    let storedCompareIds = [];
    try {
      const parsed = JSON.parse(sessionStorage.getItem('ppk.compare.selected') || '[]');
      if (Array.isArray(parsed)) storedCompareIds = parsed.filter(id => typeof id === 'string').slice(0, 4);
    } catch (_) {
      storedCompareIds = [];
    }
    const compareSelectedIds = ref(storedCompareIds);
    const compareWorkspaceOpen = ref(false);
    const comparePickerIndex = ref(null);
    const comparePickerQuery = ref('');
    const compareSelectionNotice = ref('');
    let compareBrowseScrollY = 0;
    // 按需计费目录状态。筛选数组复用现有 filters，选择状态复用 Compare。
    const catalogContextFilter = ref('');
    const catalogSearchQuery = ref('');
    const catalogRegionFilter = ref('');
    const catalogQuickFilter = ref('');
    const catalogProviderFilters = ref([]);
    const catalogModalityFilters = ref([]);
    const catalogSortOption = ref('release_date:desc');
    const catalogVisibleFields = ref(['modalities', 'input', 'output', 'cached_input', 'context_window']);
    const catalogPage = ref(1);
    const catalogPageSize = ref(50);
    // Subscription / Coding Plan 共用的 Plans Explorer 状态。
    const plansSearchQuery = ref('');
    const plansProviderFilters = ref([]);
    const plansPriceKindFilter = ref('');
    const plansPriceRangeFilter = ref('');
    const plansQuotaTypeFilter = ref('');
    const plansSortOption = ref('monthlyPrice:asc');
    const plansGroupMode = ref('provider');
    const plansExpandedIds = ref([]);
    const plansCompareOpen = ref(false);
    const plansVisibleFields = ref({
      subscription: ['monthly', 'status', 'features'],
      coding_plan: ['monthly', 'first_month', 'quota', 'features'],
    });
    let storedPlanSelections = { subscription: [], coding_plan: [] };
    try {
      const parsed = JSON.parse(sessionStorage.getItem('ppk.plans.selected') || '{}');
      for (const type of ['subscription', 'coding_plan']) {
        if (Array.isArray(parsed[type])) storedPlanSelections[type] = parsed[type].filter(id => typeof id === 'string').slice(0, 4);
      }
    } catch (_) {
      storedPlanSelections = { subscription: [], coding_plan: [] };
    }
    const plansSelectedMap = ref(storedPlanSelections);
    const plansSelectionNotice = ref('');

    // 监听 hash 变化
    window.addEventListener("hashchange", () => {
      route.value = window.location.hash || "#/";
      _viewOverride.value = null;  // 重置视图切换，恢复路由默认
      window.scrollTo(0, 0);
    });

    // 路由名称
    const routeName = computed(() => {
      const h = route.value;
      if (h === "#/" || h === "") return "home";
      if (h === "#/providers") return "providers";
      if (h === "#/compare") return "compare";
      if (h === "#/about") return "about";
      if (h.startsWith("#/billing/")) return "billing";
      if (h.startsWith("#/provider/")) return "provider";
      return "home";
    });

    // 计费类型路由（按需计费 / 订阅制 / Coding Plan）
    const billingRoute = computed(() => {
      if (routeName.value !== "billing") return null;
      return route.value.replace("#/billing/", "");
    });
    const plansMenuActive = computed(() =>
      routeName.value === 'billing' && (billingRoute.value === 'subscription' || billingRoute.value === 'coding_plan')
    );
    function togglePlansMenu() {
      // Fine-pointer devices may have opened the menu on mouseenter immediately
      // before click; keep it open instead of toggling it closed again.
      if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
        plansMenuOpen.value = true;
        return;
      }
      plansMenuOpen.value = !plansMenuOpen.value;
    }
    function openPlansMenuOnHover() {
      if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) plansMenuOpen.value = true;
    }
    function closePlansMenuOnHover() {
      if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) plansMenuOpen.value = false;
    }
    function openPlansMenuAndFocus() {
      plansMenuOpen.value = true;
      nextTick(() => document.querySelector('#nav-plans-menu [role="menuitem"]')?.focus());
    }
    function closePlansMenu(restoreFocus = false) {
      plansMenuOpen.value = false;
      if (restoreFocus) nextTick(() => document.querySelector('.nav-plans-trigger')?.focus());
    }
    function closePlansMenuOnFocusOut(event) {
      if (!event.currentTarget.contains(event.relatedTarget)) closePlansMenu();
    }
    function toggleHomePlansMenu() {
      homePlansMenuOpen.value = !homePlansMenuOpen.value;
    }
    function openHomePlansMenuAndFocus() {
      homePlansMenuOpen.value = true;
      nextTick(() => document.querySelector('#home-plans-menu [role="menuitem"]')?.focus());
    }
    function closeHomePlansMenu(restoreFocus = false) {
      homePlansMenuOpen.value = false;
      if (restoreFocus) nextTick(() => document.querySelector('.home-plans-trigger')?.focus());
    }
    function closeHomePlansMenuOnFocusOut(event) {
      if (!event.currentTarget.contains(event.relatedTarget)) closeHomePlansMenu();
    }
    watch(route, () => {
      closePlansMenu();
      closeHomePlansMenu();
    });
    watch(compareSelectedIds, ids => {
      try {
        sessionStorage.setItem('ppk.compare.selected', JSON.stringify(ids.slice(0, 4)));
      } catch (_) {
        // Storage 不可用时仍保留当前 SPA 会话内状态。
      }
    }, { deep: true });
    watch(plansSelectedMap, selections => {
      try {
        sessionStorage.setItem('ppk.plans.selected', JSON.stringify(selections));
      } catch (_) {
        // Storage 不可用时保留当前 SPA 会话状态。
      }
    }, { deep: true });

    // 厂商详情路由：#/provider/{id}，仅显示该厂商产品
    const providerRouteId = computed(() => {
      if (routeName.value !== "provider") return null;
      return route.value.replace("#/provider/", "");
    });

    // 当前选中厂商信息（providers 数组优先，PROVIDER_META 兜底）
    const currentProvider = computed(() => {
      const pid = providerRouteId.value;
      if (!pid || !data.value) return null;
      const p = data.value.providers.find(x => x.id === pid);
      if (p) return p;
      if (PROVIDER_META[pid]) {
        return { id: pid, ...PROVIDER_META[pid] };
      }
      return null;
    });

    // 厂商详情页：该厂商可用的计费方式 tab 列表（按固定顺序，只保留有产品的）
    const providerBillingTabs = computed(() => {
      if (routeName.value !== 'provider') return [];
      const order = ['per_token', 'subscription', 'coding_plan'];
      const counts = {};
      for (const r of filteredRows.value) {
        counts[r.billing_type] = (counts[r.billing_type] || 0) + 1;
      }
      return order
        .filter(bt => counts[bt] > 0)
        .map(bt => ({ key: bt, label: billingLabel(bt), count: counts[bt] }));
    });

    // 进入厂商详情页时：根据厂商 region 自动切换货币
    watch(currentProvider, (p) => {
      if (!p) return;
      // 国内厂商默认 CNY，国外厂商默认 USD
      displayCurrency.value = p.region === 'cn' ? 'CNY' : 'USD';
    });

    // 当可用 tab 列表变化时，如果当前选中的 tab 不在其中，则自动选第一个
    watch(providerBillingTabs, (tabs) => {
      if (!tabs.length) {
        providerBillingTab.value = null;
        return;
      }
      const stillValid = tabs.some(t => t.key === providerBillingTab.value);
      if (!stillValid) {
        providerBillingTab.value = tabs[0].key;
      }
    });

    // 厂商详情页：当前 tab 对应的产品列表
    const providerCurrentRows = computed(() => {
      if (routeName.value !== 'provider' || !providerBillingTab.value) return [];
      if (providerBillingTab.value === 'per_token') return providerPerTokenRows.value;
      const group = providerPlanGroups.value.find(g => g.billingType === providerBillingTab.value);
      return group ? group.products : [];
    });

    const regions = ["cn", "us", "eu"];
    const billingTypes = ["per_token", "subscription", "coding_plan"];
    const modalities = ["text", "vision", "audio", "file"];
    const compareFieldOptions = [
      { key: 'input', label: 'Input / 1M' },
      { key: 'output', label: 'Output / 1M' },
      { key: 'cached_input', label: 'Cache / 1M' },
      { key: 'context_window', label: 'Context' },
      { key: 'modalities', label: '模态' },
      { key: 'release_date', label: '发布日期' },
    ];

    const providerStatusMap = computed(() => {
      const m = {};
      if (!data.value) return m;
      for (const s of data.value.provider_status || []) {
        m[s.provider_id] = s;
      }
      return m;
    });

    const allRows = computed(() => {
      if (!data.value) return [];
      const rows = [];
      for (const p of data.value.providers) {
        const status = providerStatusMap.value[p.id] || {};
        for (const prod of p.products) {
          rows.push({
            id: `${p.id}:${prod.id}`,
            providerId: p.id,
            providerName: p.name,
            region: p.region,
            stale: status.stale === true,
            status,
            ...prod,
          });
        }
      }
      return rows;
    });

    const filteredRows = computed(() => {
      let rows = allRows.value;
      // 厂商详情页：只显示该厂商产品
      if (routeName.value === "provider" && providerRouteId.value) {
        rows = rows.filter(r => r.providerId === providerRouteId.value);
      }
      // 计费类型路由页：只显示对应计费方式
      if (billingRoute.value) {
        rows = rows.filter(r => r.billing_type === billingRoute.value);
      }
      const q = searchQuery.value.trim().toLowerCase();
      if (q) {
        rows = rows.filter(r =>
          r.providerName.toLowerCase().includes(q) ||
          (r.model || "").toLowerCase().includes(q)
        );
      }
      if (filters.value.region.length) {
        rows = rows.filter(r => filters.value.region.includes(r.region));
      }
      if (filters.value.provider.length) {
        rows = rows.filter(r => filters.value.provider.includes(r.providerId));
      }
      if (filters.value.billing.length) {
        rows = rows.filter(r => filters.value.billing.includes(r.billing_type));
      }
      if (filters.value.modality.length) {
        rows = rows.filter(r =>
          (r.modalities || []).some(m => filters.value.modality.includes(m))
        );
      }
      // sort
      rows = [...rows].sort((a, b) => {
        let va = sortValue(a, sortKey.value);
        let vb = sortValue(b, sortKey.value);
        if (va == null) va = Infinity;
        if (vb == null) vb = Infinity;
        if (typeof va === "string") {
          const cmp = sortAsc.value ? va.localeCompare(vb) : vb.localeCompare(va);
          if (cmp !== 0) return cmp;
          // 二级排序：release_date 相同时按 inputPrice 升序
          if (sortKey.value === 'release_date') {
            const pa = a.prices?.input ?? Infinity;
            const pb = b.prices?.input ?? Infinity;
            return pa - pb;
          }
          return cmp;
        }
        return sortAsc.value ? va - vb : vb - va;
      });
      return rows;
    });

    // 统一换算后的数值仅用于 Compare 页筛选与最低价判断；展示仍复用 formatPrice。
    function comparePriceValue(row, field, currency = displayCurrency.value) {
      const raw = row.prices?.[field];
      if (raw == null) return null;
      const source = row.prices?.currency || 'CNY';
      if (source === currency) return Number(raw);
      if (source === 'USD' && currency === 'CNY') return Number(raw) * USD_TO_CNY;
      if (source === 'CNY' && currency === 'USD') return Number(raw) / USD_TO_CNY;
      return Number(raw);
    }

    const compareProviderFilterList = computed(() => {
      if (!data.value) return [];
      return data.value.providers
        .map(provider => ({
          id: provider.id,
          name: provider.name,
          count: (provider.products || []).filter(product => product.billing_type === 'per_token').length,
        }))
        .filter(provider => provider.count > 0)
        .sort((a, b) => b.count - a.count);
    });

    const compareModalities = computed(() => [...new Set(
      allRows.value
        .filter(row => row.billing_type === 'per_token')
        .flatMap(row => row.modalities || [])
    )].sort());

    const compareRows = computed(() => {
      let rows = allRows.value.filter(row => row.billing_type === 'per_token');
      const q = compareSearchQuery.value.trim().toLowerCase();
      if (q) {
        rows = rows.filter(row =>
          (row.model || '').toLowerCase().includes(q) ||
          row.providerName.toLowerCase().includes(q)
        );
      }
      if (compareProviderFilters.value.length) {
        rows = rows.filter(row => compareProviderFilters.value.includes(row.providerId));
      }
      if (compareModalityFilters.value.length) {
        rows = rows.filter(row => (row.modalities || []).some(item => compareModalityFilters.value.includes(item)));
      }
      if (compareRegionFilter.value) {
        rows = rows.filter(row => row.region === compareRegionFilter.value);
      }
      if (compareContextFilter.value) {
        rows = rows.filter(row => {
          const value = row.context_window;
          if (value == null) return false;
          if (compareContextFilter.value === 'gte1000k') return value >= 1000000;
          if (compareContextFilter.value === 'gte200k') return value >= 200000;
          if (compareContextFilter.value === 'gte128k') return value >= 128000;
          if (compareContextFilter.value === 'lt128k') return value < 128000;
          return true;
        });
      }
      if (comparePriceFilter.value) {
        rows = rows.filter(row => {
          const value = comparePriceValue(row, 'input', 'CNY');
          if (value == null) return false;
          if (comparePriceFilter.value === 'lt10') return value < 10;
          if (comparePriceFilter.value === '10to50') return value >= 10 && value < 50;
          if (comparePriceFilter.value === '50to200') return value >= 50 && value < 200;
          if (comparePriceFilter.value === 'gte200') return value >= 200;
          return true;
        });
      }
      const [key, direction] = compareSortOption.value.split(':');
      const multiplier = direction === 'asc' ? 1 : -1;
      return [...rows].sort((a, b) => {
        let av;
        let bv;
        if (key === 'inputPrice') {
          av = comparePriceValue(a, 'input');
          bv = comparePriceValue(b, 'input');
        } else if (key === 'outputPrice') {
          av = comparePriceValue(a, 'output');
          bv = comparePriceValue(b, 'output');
        } else if (key === 'contextWindow') {
          av = a.context_window;
          bv = b.context_window;
        } else if (key === 'model') {
          return multiplier * (a.model || '').localeCompare(b.model || '');
        } else {
          av = a.release_date ? Date.parse(a.release_date) : null;
          bv = b.release_date ? Date.parse(b.release_date) : null;
        }
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return (av - bv) * multiplier;
      });
    });

    const catalogFieldOptions = [
      { key: 'modalities', label: '类型' },
      { key: 'input', label: 'Input / 1M' },
      { key: 'output', label: 'Output / 1M' },
      { key: 'cached_input', label: 'Cache / 1M' },
      { key: 'context_window', label: 'Context' },
      { key: 'release_date', label: '发布日期' },
    ];

    const catalogRows = computed(() => {
      let rows = allRows.value.filter(row => row.billing_type === 'per_token');
      const q = catalogSearchQuery.value.trim().toLowerCase();
      if (q) {
        rows = rows.filter(row =>
          (row.model || '').toLowerCase().includes(q) ||
          row.providerName.toLowerCase().includes(q)
        );
      }
      if (catalogProviderFilters.value.length) rows = rows.filter(row => catalogProviderFilters.value.includes(row.providerId));
      if (catalogModalityFilters.value.length) rows = rows.filter(row => (row.modalities || []).some(item => catalogModalityFilters.value.includes(item)));
      if (catalogRegionFilter.value) rows = rows.filter(row => row.region === catalogRegionFilter.value);
      if (catalogContextFilter.value) {
        rows = rows.filter(row => {
          const value = row.context_window;
          if (value == null) return false;
          if (catalogContextFilter.value === 'gte1000k') return value >= 1000000;
          if (catalogContextFilter.value === 'gte200k') return value >= 200000;
          if (catalogContextFilter.value === 'gte128k') return value >= 128000;
          if (catalogContextFilter.value === 'lt128k') return value < 128000;
          return true;
        });
      }
      if (catalogQuickFilter.value === 'under10') {
        rows = rows.filter(row => {
          const value = comparePriceValue(row, 'input', 'CNY');
          return value != null && value < 10;
        });
      } else if (catalogQuickFilter.value === 'longContext') {
        rows = rows.filter(row => row.context_window != null && row.context_window >= 200000);
      } else if (catalogQuickFilter.value === 'vision') {
        rows = rows.filter(row => (row.modalities || []).includes('vision'));
      }

      const [key, direction] = catalogSortOption.value.split(':');
      const multiplier = direction === 'asc' ? 1 : -1;
      return [...rows].sort((a, b) => {
        let av;
        let bv;
        if (key === 'inputPrice') {
          av = comparePriceValue(a, 'input');
          bv = comparePriceValue(b, 'input');
        } else if (key === 'outputPrice') {
          av = comparePriceValue(a, 'output');
          bv = comparePriceValue(b, 'output');
        } else if (key === 'cachedInput') {
          av = comparePriceValue(a, 'cached_input');
          bv = comparePriceValue(b, 'cached_input');
        } else if (key === 'contextWindow') {
          av = a.context_window;
          bv = b.context_window;
        } else if (key === 'model') {
          return multiplier * (a.model || '').localeCompare(b.model || '');
        } else {
          av = a.release_date ? Date.parse(a.release_date) : null;
          bv = b.release_date ? Date.parse(b.release_date) : null;
        }
        // 缺失值始终放在末尾，绝不按 0 参与价格排序。
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return (av - bv) * multiplier;
      });
    });

    const catalogTotalModels = computed(() => allRows.value.filter(row => row.billing_type === 'per_token').length);
    const catalogProviderCount = computed(() => new Set(
      allRows.value.filter(row => row.billing_type === 'per_token').map(row => row.providerId)
    ).size);
    const catalogTotalPages = computed(() => Math.max(1, Math.ceil(catalogRows.value.length / catalogPageSize.value)));
    const catalogPageRows = computed(() => {
      const safePage = Math.min(catalogPage.value, catalogTotalPages.value);
      const start = (safePage - 1) * catalogPageSize.value;
      return catalogRows.value.slice(start, start + catalogPageSize.value);
    });
    const catalogPageNumbers = computed(() => Array.from({ length: catalogTotalPages.value }, (_, index) => index + 1));
    const catalogActiveFilterCount = computed(() =>
      catalogProviderFilters.value.length + catalogModalityFilters.value.length +
      Number(Boolean(catalogContextFilter.value)) + Number(Boolean(catalogRegionFilter.value)) +
      Number(Boolean(catalogQuickFilter.value))
    );
    const catalogSortLabel = computed(() => ({
      'release_date:desc': '最新发布',
      'inputPrice:asc': 'Input Price ↑',
      'inputPrice:desc': 'Input Price ↓',
      'outputPrice:asc': 'Output Price ↑',
      'outputPrice:desc': 'Output Price ↓',
      'cachedInput:asc': 'Cache Price ↑',
      'cachedInput:desc': 'Cache Price ↓',
      'contextWindow:asc': 'Context ↑',
      'contextWindow:desc': 'Context ↓',
      'model:asc': '模型名称',
    })[catalogSortOption.value] || '最新发布');

    watch(() => [
      catalogSearchQuery.value,
      catalogProviderFilters.value.join(','),
      catalogModalityFilters.value.join(','),
      catalogContextFilter.value,
      catalogRegionFilter.value,
      catalogQuickFilter.value,
      catalogPageSize.value,
    ], () => { catalogPage.value = 1; });

    function clearCatalogFilters() {
      catalogSearchQuery.value = '';
      catalogProviderFilters.value = [];
      catalogModalityFilters.value = [];
      catalogContextFilter.value = '';
      catalogRegionFilter.value = '';
      catalogQuickFilter.value = '';
    }

    function toggleCatalogProvider(id) {
      const index = catalogProviderFilters.value.indexOf(id);
      if (index >= 0) catalogProviderFilters.value.splice(index, 1);
      else catalogProviderFilters.value.push(id);
    }

    function toggleCatalogModality(modality) {
      const index = catalogModalityFilters.value.indexOf(modality);
      if (index >= 0) catalogModalityFilters.value.splice(index, 1);
      else catalogModalityFilters.value.push(modality);
    }

    function toggleCatalogField(key) {
      const index = catalogVisibleFields.value.indexOf(key);
      if (index >= 0) {
        if (catalogVisibleFields.value.length > 1) catalogVisibleFields.value.splice(index, 1);
      } else {
        catalogVisibleFields.value.push(key);
      }
    }

    function sortCatalogBy(key) {
      const [currentKey, direction] = catalogSortOption.value.split(':');
      const nextDirection = currentKey === key && direction === 'asc' ? 'desc' : 'asc';
      catalogSortOption.value = `${key}:${nextDirection}`;
      catalogPage.value = 1;
    }

    function catalogSortIndicator(key) {
      const [currentKey, direction] = catalogSortOption.value.split(':');
      if (currentKey !== key) return '';
      return direction === 'asc' ? '↑' : '↓';
    }

    function goToCompareWorkspace() {
      if (compareSelectedIds.value.length < 2) {
        compareSelectionNotice.value = '请至少选择 2 个模型';
        return;
      }
      compareBrowseScrollY = 0;
      compareWorkspaceOpen.value = true;
      compareSelectionNotice.value = '';
      window.location.hash = '#/compare';
    }

    function planPriceValue(row, field = 'monthly_price', currency = displayCurrency.value) {
      const raw = row.prices?.[field];
      if (raw == null) return null;
      const source = row.prices?.currency || 'CNY';
      if (source === currency) return Number(raw);
      if (source === 'USD' && currency === 'CNY') return Number(raw) * USD_TO_CNY;
      if (source === 'CNY' && currency === 'USD') return Number(raw) / USD_TO_CNY;
      return Number(raw);
    }

    function formatPlanPrice(row, field = 'monthly_price') {
      const value = planPriceValue(row, field);
      if (value == null) return '—';
      if (field === 'monthly_price' && Number(row.prices?.monthly_price) === 0) return '免费';
      const currency = rowDisplayCurrency(row);
      const symbol = currencySymbols[currency] || `${currency} `;
      const rounded = Math.abs(value) >= 100 ? value.toFixed(value % 1 ? 1 : 0) : value.toFixed(value % 1 ? 2 : 0);
      return `${symbol}${rounded}`;
    }

    function planQuotaType(row) {
      const unit = row.prices?.quota_unit;
      return ({
        credits_in_billions: 'credits',
        calls_per_month: 'calls',
        prompts_per_5h: 'prompts',
        prompts_per_month: 'prompts',
        afp_per_month: 'afp',
        USD: 'monetary',
        base: 'base',
      })[unit] || 'other';
    }

    function formatPlanQuota(row) {
      const price = row.prices || {};
      const quota = price.included_quota;
      const unit = price.quota_unit;
      if (quota == null || unit == null) return '—';
      const number = Number(quota).toLocaleString('zh-CN');
      if (unit === 'credits_in_billions') return `${number}B Credits`;
      if (unit === 'calls_per_month') return `${number} 次 / 月`;
      if (unit === 'prompts_per_5h') return `${number} 次 / 5 小时`;
      if (unit === 'prompts_per_month') return `${number} 次 / 月`;
      if (unit === 'afp_per_month') return `${number} AFP / 月`;
      if (unit === 'USD') return `$${number} Credits`;
      if (unit === 'base') return `${number}× 基础额度`;
      return `${number} ${unit}`;
    }

    const plansBaseRows = computed(() => {
      if (billingRoute.value !== 'subscription' && billingRoute.value !== 'coding_plan') return [];
      return allRows.value.filter(row => row.billing_type === billingRoute.value);
    });
    const plansProviderCount = computed(() => new Set(plansBaseRows.value.map(row => row.providerId)).size);
    const plansProviderOptions = computed(() => {
      const counts = new Map();
      for (const row of plansBaseRows.value) {
        if (!counts.has(row.providerId)) counts.set(row.providerId, { id: row.providerId, name: row.providerName, count: 0 });
        counts.get(row.providerId).count += 1;
      }
      return [...counts.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
    });
    const plansQuotaTypeOptions = computed(() => {
      if (billingRoute.value !== 'coding_plan') return [];
      const labels = { credits: 'Credits', calls: '调用次数', prompts: 'Prompts', afp: 'AFP', monetary: '金额 Credits', base: '基础额度倍数', other: '其他' };
      const types = new Set(plansBaseRows.value.map(planQuotaType));
      return [...types].map(key => ({ key, label: labels[key] || key }));
    });

    const plansRows = computed(() => {
      let rows = [...plansBaseRows.value];
      const q = plansSearchQuery.value.trim().toLowerCase();
      if (q) rows = rows.filter(row => (row.model || '').toLowerCase().includes(q) || row.providerName.toLowerCase().includes(q));
      if (plansProviderFilters.value.length) rows = rows.filter(row => plansProviderFilters.value.includes(row.providerId));
      if (plansPriceKindFilter.value === 'free') rows = rows.filter(row => Number(row.prices?.monthly_price) === 0);
      if (plansPriceKindFilter.value === 'paid') rows = rows.filter(row => Number(row.prices?.monthly_price) > 0);
      if (plansPriceRangeFilter.value) {
        rows = rows.filter(row => {
          const value = planPriceValue(row, 'monthly_price', 'CNY');
          if (value == null) return false;
          if (plansPriceRangeFilter.value === 'lt50') return value < 50;
          if (plansPriceRangeFilter.value === '50to150') return value >= 50 && value < 150;
          if (plansPriceRangeFilter.value === '150to500') return value >= 150 && value < 500;
          if (plansPriceRangeFilter.value === 'gte500') return value >= 500;
          return true;
        });
      }
      if (plansQuotaTypeFilter.value) rows = rows.filter(row => planQuotaType(row) === plansQuotaTypeFilter.value);
      const direction = plansSortOption.value.endsWith(':desc') ? -1 : 1;
      return rows.sort((a, b) => {
        const av = planPriceValue(a, 'monthly_price');
        const bv = planPriceValue(b, 'monthly_price');
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return (av - bv) * direction || (a.model || '').localeCompare(b.model || '');
      });
    });

    const plansGroups = computed(() => {
      if (plansGroupMode.value === 'none') return [{ id: 'all', name: '', rows: plansRows.value }];
      const groups = new Map();
      for (const row of plansRows.value) {
        if (!groups.has(row.providerId)) groups.set(row.providerId, { id: row.providerId, name: row.providerName, rows: [] });
        groups.get(row.providerId).rows.push(row);
      }
      return [...groups.values()];
    });

    const currentPlansVisibleFields = computed(() => plansVisibleFields.value[billingRoute.value] || []);
    const currentPlanSelectedIds = computed(() => plansSelectedMap.value[billingRoute.value] || []);
    const currentPlanSelectedRows = computed(() => currentPlanSelectedIds.value
      .map(id => plansBaseRows.value.find(row => row.id === id))
      .filter(Boolean));
    const plansActiveFilterCount = computed(() => plansProviderFilters.value.length +
      Number(Boolean(plansPriceKindFilter.value)) + Number(Boolean(plansPriceRangeFilter.value)) + Number(Boolean(plansQuotaTypeFilter.value)));
    const plansSortLabel = computed(() => plansSortOption.value.endsWith(':desc') ? '月费从高到低' : '月费从低到高');

    function togglePlansProvider(id) {
      const index = plansProviderFilters.value.indexOf(id);
      if (index >= 0) plansProviderFilters.value.splice(index, 1);
      else plansProviderFilters.value.push(id);
    }
    function clearPlansFilters() {
      plansSearchQuery.value = '';
      plansProviderFilters.value = [];
      plansPriceKindFilter.value = '';
      plansPriceRangeFilter.value = '';
      plansQuotaTypeFilter.value = '';
    }
    function togglePlansField(key) {
      const fields = currentPlansVisibleFields.value;
      const index = fields.indexOf(key);
      if (index >= 0) {
        if (fields.length > 1) fields.splice(index, 1);
      } else fields.push(key);
    }
    function closePlansToolbarMenu(event) {
      event?.currentTarget?.closest('details')?.removeAttribute('open');
    }
    function setPlansSortOption(value, event) {
      plansSortOption.value = value;
      closePlansToolbarMenu(event);
    }
    function setPlansGroupMode(value, event) {
      plansGroupMode.value = value;
      closePlansToolbarMenu(event);
    }
    function togglePlanExpanded(id) {
      const index = plansExpandedIds.value.indexOf(id);
      if (index >= 0) plansExpandedIds.value.splice(index, 1);
      else plansExpandedIds.value.push(id);
    }
    function isPlanSelected(row) { return currentPlanSelectedIds.value.includes(row.id); }
    function togglePlanSelection(row) {
      const ids = plansSelectedMap.value[billingRoute.value];
      const index = ids.indexOf(row.id);
      plansSelectionNotice.value = '';
      if (index >= 0) ids.splice(index, 1);
      else if (ids.length < 4) ids.push(row.id);
      else plansSelectionNotice.value = '最多同时选择 4 个套餐';
      if (ids.length < 2) plansCompareOpen.value = false;
    }
    function removePlanSelection(id) {
      const ids = plansSelectedMap.value[billingRoute.value];
      const index = ids.indexOf(id);
      if (index >= 0) ids.splice(index, 1);
      plansSelectionNotice.value = '';
      if (ids.length < 2) plansCompareOpen.value = false;
    }
    function clearPlanSelection() {
      plansSelectedMap.value[billingRoute.value] = [];
      plansCompareOpen.value = false;
      plansSelectionNotice.value = '';
    }
    function openPlansCompare() {
      if (currentPlanSelectedRows.value.length < 2) {
        plansSelectionNotice.value = '请至少选择 2 个套餐';
        return;
      }
      plansCompareOpen.value = true;
      plansSelectionNotice.value = '';
      nextTick(() => window.scrollTo({ top: Math.max(document.querySelector('.plans-explorer-page')?.offsetTop - 72 || 0, 0), behavior: 'smooth' }));
    }
    function closePlansCompare() { plansCompareOpen.value = false; }
    watch(billingRoute, (next, previous) => {
      if (next === previous) return;
      if ((next === 'subscription' || next === 'coding_plan') && (previous === 'subscription' || previous === 'coding_plan')) {
        clearPlansFilters();
        plansExpandedIds.value = [];
        plansCompareOpen.value = false;
      }
    });
    watch(allRows, rows => {
      if (!rows.length) return;
      for (const type of ['subscription', 'coding_plan']) {
        const valid = new Set(rows.filter(row => row.billing_type === type).map(row => row.id));
        plansSelectedMap.value[type] = (plansSelectedMap.value[type] || []).filter(id => valid.has(id)).slice(0, 4);
      }
    }, { immediate: true });

    const compareSelectedRows = computed(() =>
      compareSelectedIds.value
        .map(id => allRows.value.find(row => row.id === id && row.billing_type === 'per_token'))
        .filter(Boolean)
    );
    watch(allRows, rows => {
      if (!rows.length) return;
      const validIds = new Set(rows.filter(row => row.billing_type === 'per_token').map(row => row.id));
      compareSelectedIds.value = compareSelectedIds.value.filter(id => validIds.has(id)).slice(0, 4);
    }, { immediate: true });

    const comparePickerRows = computed(() => {
      const q = comparePickerQuery.value.trim().toLowerCase();
      const currentId = comparePickerIndex.value == null ? null : compareSelectedIds.value[comparePickerIndex.value];
      const selectedElsewhere = new Set(compareSelectedIds.value.filter(id => id !== currentId));
      return allRows.value
        .filter(row => row.billing_type === 'per_token' && !selectedElsewhere.has(row.id))
        .filter(row => !q || (row.model || '').toLowerCase().includes(q) || row.providerName.toLowerCase().includes(q))
        .slice(0, 60);
    });

    const compareActiveFilterCount = computed(() =>
      compareProviderFilters.value.length + compareModalityFilters.value.length +
      Number(Boolean(compareContextFilter.value)) + Number(Boolean(comparePriceFilter.value)) +
      Number(Boolean(compareRegionFilter.value))
    );

    function isCompareSelected(row) {
      return compareSelectedIds.value.includes(row.id);
    }

    function toggleCompareSelection(row) {
      const index = compareSelectedIds.value.indexOf(row.id);
      compareSelectionNotice.value = '';
      if (index >= 0) {
        compareSelectedIds.value.splice(index, 1);
        if (compareSelectedIds.value.length < 2) compareWorkspaceOpen.value = false;
        return;
      }
      if (compareSelectedIds.value.length >= 4) {
        compareSelectionNotice.value = '最多同时选择 4 个模型';
        return;
      }
      compareSelectedIds.value.push(row.id);
    }

    function removeCompareSelection(id) {
      const index = compareSelectedIds.value.indexOf(id);
      if (index >= 0) compareSelectedIds.value.splice(index, 1);
      comparePickerIndex.value = null;
      comparePickerQuery.value = '';
      compareSelectionNotice.value = '';
      if (compareSelectedIds.value.length < 2 && compareWorkspaceOpen.value) closeCompareWorkspace();
    }

    function clearCompareSelection() {
      compareSelectedIds.value = [];
      compareWorkspaceOpen.value = false;
      comparePickerIndex.value = null;
      compareSelectionNotice.value = '';
    }

    function startCompareWorkspace() {
      if (compareSelectedIds.value.length < 2) {
        compareSelectionNotice.value = '请至少选择 2 个模型';
        return;
      }
      compareBrowseScrollY = window.scrollY;
      compareWorkspaceOpen.value = true;
      compareSelectionNotice.value = '';
      nextTick(() => {
        const page = document.querySelector('.compare-page');
        if (!page) return;
        window.scrollTo({ top: Math.max(page.offsetTop - 72, 0), behavior: 'smooth' });
      });
    }

    function closeCompareWorkspace() {
      compareWorkspaceOpen.value = false;
      comparePickerIndex.value = null;
      comparePickerQuery.value = '';
      nextTick(() => window.scrollTo({ top: compareBrowseScrollY, behavior: 'smooth' }));
    }

    function openComparePicker(index) {
      comparePickerIndex.value = comparePickerIndex.value === index ? null : index;
      comparePickerQuery.value = '';
      if (comparePickerIndex.value != null) {
        nextTick(() => document.querySelector(`#compare-picker-${index} input`)?.focus());
      }
    }

    function selectCompareReplacement(row) {
      if (comparePickerIndex.value == null) return;
      compareSelectedIds.value.splice(comparePickerIndex.value, 1, row.id);
      comparePickerIndex.value = null;
      comparePickerQuery.value = '';
    }

    function closeComparePicker(restoreFocus = false) {
      const index = comparePickerIndex.value;
      comparePickerIndex.value = null;
      comparePickerQuery.value = '';
      if (restoreFocus && index != null) nextTick(() => document.querySelector(`[data-compare-picker-trigger="${index}"]`)?.focus());
    }

    function clearCompareFilters() {
      compareSearchQuery.value = '';
      compareProviderFilters.value = [];
      compareModalityFilters.value = [];
      compareContextFilter.value = '';
      comparePriceFilter.value = '';
      compareRegionFilter.value = '';
    }

    function toggleCompareProvider(id) {
      const index = compareProviderFilters.value.indexOf(id);
      if (index >= 0) compareProviderFilters.value.splice(index, 1);
      else compareProviderFilters.value.push(id);
    }

    function toggleCompareModality(modality) {
      const index = compareModalityFilters.value.indexOf(modality);
      if (index >= 0) compareModalityFilters.value.splice(index, 1);
      else compareModalityFilters.value.push(modality);
    }

    function toggleCompareField(key) {
      const index = compareVisibleFields.value.indexOf(key);
      if (index >= 0) {
        if (compareVisibleFields.value.length > 1) compareVisibleFields.value.splice(index, 1);
      } else {
        compareVisibleFields.value.push(key);
      }
    }

    function isCompareLowest(row, field) {
      const values = compareSelectedRows.value
        .map(item => comparePriceValue(item, field))
        .filter(value => value != null && Number.isFinite(value));
      if (values.length < 2) return false;
      const value = comparePriceValue(row, field);
      return value != null && value === Math.min(...values);
    }

    // 厂商总览列表（含产品数和状态）
    const providerList = computed(() => {
      if (!data.value) return [];
      return data.value.providers.map(p => {
        const status = providerStatusMap.value[p.id] || {};
        const products = p.products || [];
        // 计费方式分布：{per_token: bool, subscription: bool, coding_plan: bool}
        const billingTypes = { per_token: false, subscription: false, coding_plan: false };
        for (const prod of products) {
          if (billingTypes.hasOwnProperty(prod.billing_type)) {
            billingTypes[prod.billing_type] = true;
          }
        }
        return {
          ...p,
          productCount: products.length,
          billingTypes,
          stale: status.stale === true,
          statusText: status.status === "ok" ? "正常" : (status.stale ? "数据过期" : "抓取失败"),
          statusOk: status.status === "ok",
        };
      });
    });

    // 首页厂商目录仅展示模型 / API / 云服务商；开发工具保留在 AI Coding Ecosystem。
    // 模型数来自各厂商真实 per_token 产品中的唯一 model 字段，不影响全站厂商数据。
    const homeProviderList = computed(() =>
      providerList.value
        .filter(p => !CODING_TOOL_PROVIDER_IDS.has(p.id))
        .map(p => ({
          ...p,
          modelCount: new Set(
            (p.products || [])
              .filter(product => product.billing_type === 'per_token' && product.model)
              .map(product => product.model)
          ).size,
        }))
    );

    // 简短计费方式标签（用于厂商卡片 chips）
    function billingLabelShort(b) {
      return { per_token: "Token", subscription: "订阅", coding_plan: "Coding" }[b] || b;
    }

    // 全局搜索匹配列表（用于下拉建议 + 回车跳转到第一个匹配项）
    const searchMatches = computed(() => {
      const q = globalSearch.value.trim().toLowerCase();
      if (!q) return [];
      const list = providerList.value || [];
      return list.filter(p => {
        const name = (p.name || '').toLowerCase();
        const nameEn = (p.name_en || '').toLowerCase();
        const id = (p.id || '').toLowerCase();
        return name.includes(q) || nameEn.includes(q) || id.includes(q);
      });
    });
    // 下拉建议最多 8 条
    const searchSuggestions = computed(() => searchMatches.value.slice(0, 8));

    // 回车跳转到第一个匹配项；无匹配则跳转到厂商总览页
    function goProvider(pid) {
      globalSearch.value = "";
      searchFocused.value = false;
      goHash(`#/provider/${pid}`);
    }
    function searchSubmit() {
      const matches = searchMatches.value;
      if (matches.length > 0) {
        goProvider(matches[0].id);
      } else {
        goHash('#/providers');
        globalSearch.value = "";
        searchFocused.value = false;
      }
    }

    // 厂商总览页：按地区分组（国内 cn / 国外 us+eu），支持本地搜索过滤
    const providerSearch = ref('');
    const providerListByRegion = computed(() => {
      const q = providerSearch.value.trim().toLowerCase();
      const list = q
        ? providerList.value.filter(p =>
            (p.name || '').toLowerCase().includes(q) ||
            (p.name_en || '').toLowerCase().includes(q) ||
            (p.id || '').toLowerCase().includes(q)
          )
        : providerList.value;
      const cn = list.filter(p => p.region === 'cn');
      const intl = list.filter(p => p.region !== 'cn');
      return { cn, intl, total: list.length };
    });

    // 按厂商分组的卡片视图数据（兼容旧引用，保留但不再用于渲染）
    const groupedRows = computed(() => {
      const rows = filteredRows.value;
      const map = new Map();
      for (const r of rows) {
        if (!map.has(r.providerId)) {
          map.set(r.providerId, {
            providerId: r.providerId,
            providerName: r.providerName,
            region: r.region,
            stale: r.stale,
            status: r.status,
            products: [],
          });
        }
        map.get(r.providerId).products.push(r);
      }
      return [...map.values()];
    });

    // billing 路由扁平化产品列表：一张卡片一个套餐
    // 按厂商分组，同厂商内按月费升序
    const billingFlatProducts = computed(() => {
      const rows = filteredRows.value.slice();
      // 稳定排序：厂商名 → 月费
      rows.sort((a, b) => {
        const pa = a.providerName || '';
        const pb = b.providerName || '';
        if (pa !== pb) return pa.localeCompare(pb, 'zh');
        const ma = a.prices?.monthly_price ?? Infinity;
        const mb = b.prices?.monthly_price ?? Infinity;
        return ma - mb;
      });
      return rows;
    });

    // billing 路由：按实际货币分组（CNY / USD），同一厂商可能两边都有
    const billingCurrencyTab = ref('CNY');

    const billingCnyCount = computed(() => {
      if (routeName.value !== 'billing') return 0;
      return filteredRows.value.filter(r => r.prices?.currency === 'CNY').length;
    });
    const billingUsdCount = computed(() => {
      if (routeName.value !== 'billing') return 0;
      return filteredRows.value.filter(r => r.prices?.currency === 'USD').length;
    });

    // 进入 billing 路由时：默认显示产品数量多的货币 Tab
    watch(billingRoute, () => {
      if (routeName.value !== 'billing') return;
      billingCurrencyTab.value = billingCnyCount.value >= billingUsdCount.value ? 'CNY' : 'USD';
    });

    // billing 路由表格用：按选中货币筛选
    const displayRows = computed(() => {
      if (routeName.value !== 'billing') return filteredRows.value;
      return filteredRows.value.filter(r => r.prices?.currency === billingCurrencyTab.value);
    });

    // billing 路由卡片用：按选中货币筛选
    const billingCardGroups = computed(() => {
      if (routeName.value !== 'billing') return [];
      const products = billingFlatProducts.value.filter(p => p.prices?.currency === billingCurrencyTab.value);
      return [{ label: billingCurrencyTab.value, products }];
    });

    // 厂商详情页：按计费方式分区展示
    // providerPerTokenRows - 该厂商的 per_token 产品（用 8 列表格展示）
    // providerPlanGroups - 该厂商的 subscription/coding_plan 产品，按 billing_type 分组（用卡片展示）
    const providerPerTokenRows = computed(() => {
      if (routeName.value !== 'provider') return [];
      return filteredRows.value.filter(r => r.billing_type === 'per_token');
    });
    const providerPlanGroups = computed(() => {
      if (routeName.value !== 'provider') return [];
      const rows = filteredRows.value.filter(r => r.billing_type !== 'per_token');
      const groups = {};
      for (const r of rows) {
        if (!groups[r.billing_type]) {
          groups[r.billing_type] = {
            billingType: r.billing_type,
            label: billingLabel(r.billing_type),
            products: [],
          };
        }
        groups[r.billing_type].products.push(r);
      }
      // 保持 subscription 在前、coding_plan 在后
      const order = ['subscription', 'coding_plan'];
      return order.map(bt => groups[bt]).filter(g => g);
    });

    // 筛选区厂商列表：按产品数降序，排除 0 产品的厂商
    // billing 路由下只显示当前 billing_type 有产品的厂商
    const providerFilterList = computed(() => {
      if (!data.value) return [];
      return data.value.providers
        .map(p => ({
          id: p.id,
          name: p.name,
          count: billingRoute.value
            ? (p.products || []).filter(pr => pr.billing_type === billingRoute.value).length
            : (p.products || []).length,
        }))
        .filter(p => p.count > 0)
        .sort((a, b) => b.count - a.count);
    });

    // Hero 动态呼吸图标集合：包含所有厂商（含抓取失败的），
    // 合并 providers 数组和 provider_status 中的 id，用 PROVIDER_META 补全名称
    const allProvidersForOrbit = computed(() => {
      if (!data.value) return [];
      const seen = new Set();
      const result = [];
      // 先加 providers 数组里的
      for (const p of data.value.providers) {
        if (!seen.has(p.id) && !CODING_TOOL_PROVIDER_IDS.has(p.id)) {
          seen.add(p.id);
          result.push(p);
        }
      }
      // 再加 provider_status 里有但 providers 里没有的（抓取失败的厂商）
      for (const s of (data.value.provider_status || [])) {
        const pid = s.provider_id;
        if (!seen.has(pid) && !CODING_TOOL_PROVIDER_IDS.has(pid)) {
          seen.add(pid);
          const meta = PROVIDER_META[pid] || { name: pid, name_en: pid, region: 'cn' };
          result.push({ id: pid, ...meta });
        }
      }
      // 最后加 PROVIDER_META 中定义但尚未出现在数据中的厂商（新增厂商，尚无适配器）
      for (const [pid, meta] of Object.entries(PROVIDER_META)) {
        if (!seen.has(pid) && !CODING_TOOL_PROVIDER_IDS.has(pid)) {
          seen.add(pid);
          result.push({ id: pid, ...meta });
        }
      }
      return result;
    });

    // 图标加载失败时用品牌色+首字母占位
    function onIconError(e, providerId) {
      const name = String(
        (data.value?.providers.find(p => p.id === providerId)?.name) || providerId || "?"
      );
      const letter = name[0] || "?";
      const color = PROVIDER_COLORS[providerId] || "#165dff";
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect width="48" height="48" rx="8" fill="${color}"/><text x="24" y="33" font-size="26" font-weight="700" fill="white" text-anchor="middle" font-family="sans-serif">${letter}</text></svg>`;
      e.target.src = "data:image/svg+xml;utf8," + encodeURIComponent(svg);
    }

    // 跳转到指定 hash 路由
    function goHash(hash) {
      window.location.hash = hash;
    }

    function sortValue(row, key) {
      if (key === "providerName") return row.providerName;
      if (key === "model") return row.model || "";
      if (key === "billing_type") return row.billing_type;
      if (key === "modalities") return (row.modalities || []).join(", ");
      if (key === "inputPrice") return row.prices?.input;
      if (key === "outputPrice") return row.prices?.output;
      if (key === "cachedInput") return row.prices?.cached_input;
      if (key === "contextWindow") return row.context_window;
      if (key === "monthlyPrice") return row.prices?.monthly_price;
      if (key === "release_date") return row.release_date || "";
      return null;
    }

    const currentRow = computed(() => {
      if (!expanded.value) return null;
      return allRows.value.find(r => r.id === expanded.value);
    });

    const totalProducts = computed(() => allRows.value.length);
    const staleCount = computed(() => {
      if (!data.value) return 0;
      return (data.value.provider_status || []).filter(s => s.stale).length;
    });
    const successCount = computed(() => {
      if (!data.value) return 0;
      return (data.value.provider_status || []).filter(s => !s.stale).length;
    });
    // 首页 Pricing Taxonomy：按需计费，以及由 Subscription + Coding Plan 组成的 Plans。
    const perTokenCount = computed(() =>
      allRows.value.filter(r => r.billing_type === 'per_token' && !r.stale).length
    );
    const subscriptionCount = computed(() =>
      allRows.value.filter(r => r.billing_type === 'subscription' && !r.stale).length
    );
    const codingPlanCount = computed(() =>
      allRows.value.filter(r => r.billing_type === 'coding_plan' && !r.stale).length
    );
    const plansCount = computed(() => subscriptionCount.value + codingPlanCount.value);

    // 首页只展示两个顶层价格入口；示例名称从当前真实数据中派生。
    const billingSlides = computed(() => {
      const perTokenRows = allRows.value.filter(row => row.billing_type === 'per_token' && !row.stale);
      const providerExamples = ['openai', 'anthropic', 'google']
        .map(providerId => perTokenRows.find(row => row.providerId === providerId)?.providerName)
        .filter(Boolean)
        .map(name => `${name} API`);
      if (providerExamples.length < 3) {
        for (const row of perTokenRows) {
          const label = `${row.providerName} API`;
          if (!providerExamples.includes(label)) providerExamples.push(label);
          if (providerExamples.length === 3) break;
        }
      }
      const planRows = allRows.value.filter(row =>
        (row.billing_type === 'subscription' || row.billing_type === 'coding_plan') && !row.stale && row.model
      );
      const preferredPlans = ['ChatGPT Plus', 'Cursor Pro', 'GLM Coding Plan Pro'];
      const planExamples = preferredPlans
        .map(name => planRows.find(row => row.model === name)?.model)
        .filter(Boolean);
      if (planExamples.length < 3) {
        for (const row of planRows) {
          if (!planExamples.includes(row.model)) planExamples.push(row.model);
          if (planExamples.length === 3) break;
        }
      }
      return [
        {
        index: '01',
        label: 'Pay As You Go',
        name: '按需计费',
        value: '用多少，付多少',
        desc: '输入、输出与缓存 Token 分别计价，调用后按实际用量结算。',
        examples: providerExamples,
        exampleLabel: '常见服务',
        image: 'image/Pay as you go.png',
      },
      {
        index: '02',
        label: 'Plans',
        name: '套餐',
        value: '固定费用，获得套餐权益',
        desc: '按月付费或预先购买固定额度，在有效期内使用对应权益。',
        examples: planExamples,
        exampleLabel: '常见套餐',
        image: 'image/Subscribe.png',
      },
      ];
    });
    const billingSlideIndex = ref(0);
    const billingSlideDir = ref('next');
    function goBillingSlide(i) {
      const total = billingSlides.value.length;
      billingSlideDir.value = i > billingSlideIndex.value ? 'next' : 'prev';
      // 循环边界
      if (i < 0) i = total - 1;
      if (i >= total) i = 0;
      billingSlideIndex.value = i;
    }

    // 首页价格预览：每个模型原厂只取旗舰系列的最新一款，并按人民币输入价格降序排列。
    // 返回 8 条后由 CSS 根据视口显示桌面 8 / 平板 6 / 移动端 4 条。
    const homePreviewRows = computed(() => {
      const rows = allRows.value.filter(r =>
        r.billing_type === 'per_token' && !r.stale && r.prices &&
        r.prices.input != null && r.prices.output != null
      );
      const newestFirst = (a, b) => {
        const dateCompare = (b.release_date || '').localeCompare(a.release_date || '');
        return dateCompare || a.model.localeCompare(b.model, 'zh');
      };
      const selected = HOME_FLAGSHIP_PROVIDER_RULES.flatMap(({ providerId, modelPatterns }) => {
        const providerRows = rows.filter(row => row.providerId === providerId);
        for (const pattern of modelPatterns) {
          const latest = providerRows.filter(row => pattern.test(row.model)).sort(newestFirst)[0];
          if (latest) return [latest];
        }
        return [];
      });
      const priceInCny = (row, field) => {
        const value = Number(row.prices?.[field]);
        if (!Number.isFinite(value)) return -Infinity;
        return row.prices.currency === 'USD' ? value * USD_TO_CNY : value;
      };
      selected.sort((a, b) =>
        priceInCny(b, 'input') - priceInCny(a, 'input') ||
        priceInCny(b, 'output') - priceInCny(a, 'output') ||
        (b.release_date || '').localeCompare(a.release_date || '') ||
        a.providerName.localeCompare(b.providerName, 'zh')
      );
      return selected;
    });

    // 首页真实模型对比：默认复用价格预览中价格最高、厂商不重复的前三项。
    const homeCompareDefaults = computed(() => homePreviewRows.value.slice(0, 3));
    const homeCompareSelectedIds = ref([]);
    const homeModelPickerIndex = ref(-1);
    const homeModelPickerQuery = ref('');
    const homeCompareCandidates = computed(() =>
      allRows.value
        .filter(row => row.billing_type === 'per_token' && !row.stale && row.model && row.prices)
        .sort((a, b) => {
          const dateCompare = (b.release_date || '').localeCompare(a.release_date || '');
          if (dateCompare) return dateCompare;
          const providerCompare = a.providerName.localeCompare(b.providerName, 'zh');
          return providerCompare || a.model.localeCompare(b.model, 'zh');
        })
    );
    watch(homeCompareDefaults, defaults => {
      const validIds = new Set(homeCompareCandidates.value.map(row => row.id));
      const next = homeCompareSelectedIds.value.filter(id => validIds.has(id)).slice(0, 3);
      for (const row of defaults) {
        if (!next.includes(row.id)) next.push(row.id);
        if (next.length === 3) break;
      }
      homeCompareSelectedIds.value = next;
    }, { immediate: true });
    const homeCompareRows = computed(() =>
      homeCompareSelectedIds.value
        .map(id => homeCompareCandidates.value.find(row => row.id === id))
        .filter(Boolean)
    );
    function homeCompareCnyPrice(row, field) {
      const raw = row.prices?.[field];
      if (raw == null || !Number.isFinite(Number(raw))) return null;
      const value = Number(raw);
      return row.prices.currency === 'USD' ? value * USD_TO_CNY : value;
    }
    const homeCompareLowestPrices = computed(() => {
      const result = {};
      for (const field of ['input', 'output', 'cached_input']) {
        const values = homeCompareRows.value
          .map(row => homeCompareCnyPrice(row, field))
          .filter(value => value != null);
        result[field] = values.length ? Math.min(...values) : null;
      }
      return result;
    });
    function isHomeCompareLowest(row, field) {
      const value = homeCompareCnyPrice(row, field);
      const lowest = homeCompareLowestPrices.value[field];
      return value != null && lowest != null && Math.abs(value - lowest) < 1e-9;
    }
    function homeModelPickerRows(columnIndex) {
      const query = homeModelPickerQuery.value.trim().toLowerCase();
      const selectedElsewhere = new Set(
        homeCompareSelectedIds.value.filter((id, index) => index !== columnIndex)
      );
      return homeCompareCandidates.value
        .filter(row => !selectedElsewhere.has(row.id))
        .filter(row => !query || row.model.toLowerCase().includes(query) || row.providerName.toLowerCase().includes(query))
        .slice(0, 40);
    }
    function openHomeModelPicker(index) {
      if (homeModelPickerIndex.value === index) {
        homeModelPickerIndex.value = -1;
        return;
      }
      homeModelPickerIndex.value = index;
      homeModelPickerQuery.value = '';
      nextTick(() => document.querySelector(`[data-home-picker="${index}"] input`)?.focus());
    }
    function selectHomeCompareModel(index, row) {
      if (homeCompareSelectedIds.value.some((id, selectedIndex) => selectedIndex !== index && id === row.id)) return;
      const next = [...homeCompareSelectedIds.value];
      next[index] = row.id;
      homeCompareSelectedIds.value = next;
      homeModelPickerIndex.value = -1;
      homeModelPickerQuery.value = '';
      nextTick(() => document.querySelector(`[data-home-model-trigger="${index}"]`)?.focus());
    }
    function addHomePreviewToCompare(row) {
      if (!row?.id || !homeCompareCandidates.value.some(candidate => candidate.id === row.id)) return;
      if (!homeCompareSelectedIds.value.includes(row.id)) {
        const next = [...homeCompareSelectedIds.value];
        if (next.length < 3) next.push(row.id);
        else next[2] = row.id;
        homeCompareSelectedIds.value = next;
      }
      homeModelPickerIndex.value = -1;
      homeModelPickerQuery.value = '';
      nextTick(() => {
        const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        document.querySelector('#home-model-compare')?.scrollIntoView({
          behavior: reduceMotion ? 'auto' : 'smooth',
          block: 'start',
        });
      });
    }
    function closeHomeModelPicker() {
      homeModelPickerIndex.value = -1;
    }
    function handleHomeModelPickerKeydown(event) {
      if (event.key === 'Escape') {
        const index = homeModelPickerIndex.value;
        closeHomeModelPicker();
        nextTick(() => document.querySelector(`[data-home-model-trigger="${index}"]`)?.focus());
        return;
      }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      const options = [...event.currentTarget.querySelectorAll('.home-model-option:not(:disabled)')];
      if (!options.length) return;
      const current = options.indexOf(document.activeElement);
      const offset = event.key === 'ArrowDown' ? 1 : -1;
      const nextIndex = current === -1 ? (event.key === 'ArrowDown' ? 0 : options.length - 1) : (current + offset + options.length) % options.length;
      options[nextIndex].focus();
    }

    // 首页套餐预览由数据层显式策展，不再跨币种比较月费或按最低价自动选品。
    const homePlanRows = computed(() =>
      allRows.value.filter(r =>
        (r.billing_type === 'coding_plan' || r.billing_type === 'subscription') &&
        r.featured_on_home === true &&
        r.prices?.monthly_price != null
      )
    );

    // Hero ticker: 最低价卡片 + 随机展示 2 张
    const perTokenRows = computed(() =>
      allRows.value.filter(r => r.billing_type === 'per_token' && r.prices && r.prices.input != null && !r.stale)
    );
    const tickerFeatured = computed(() => {
      if (!perTokenRows.value.length) return null;
      const sorted = [...perTokenRows.value].sort((a, b) => {
        const pa = a.prices.currency === 'USD' ? a.prices.input * 7.2 : a.prices.input;
        const pb = b.prices.currency === 'USD' ? b.prices.input * 7.2 : b.prices.input;
        return pa - pb;
      });
      return sorted[0];
    });
    const tickerCards = computed(() => {
      const featured = tickerFeatured.value;
      const pool = perTokenRows.value.filter(r => !featured || r.id !== featured.id);
      const seen = new Set();
      const result = [];
      for (const r of pool) {
        if (seen.has(r.providerId)) continue;
        seen.add(r.providerId);
        result.push(r);
        if (result.length >= 2) break;
      }
      return result;
    });

    // Hero 右侧：厂商图标环形呼吸布局
    // 11 个代表厂商按 2 / 4 / 5 分布在三层轨道，减少内圈拥挤并平衡上下视觉重心。
    const orbitStyle = (index, total) => {
      const innerCount = Math.min(2, total);
      const middleCount = Math.min(4, Math.max(total - innerCount, 0));
      const outerCount = Math.max(total - innerCount - middleCount, 0);
      const layerCounts = [innerCount, middleCount, outerCount];
      const layerStarts = [0, innerCount, innerCount + middleCount];
      const layer = index < layerStarts[1] ? 0 : index < layerStarts[2] ? 1 : 2;
      const layerCount = layerCounts[layer];
      const layerIndex = index - layerStarts[layer];
      const radii = [95, 150, 205];
      const radius = radii[layer];
      // 每层使用不同起始角：保持等角间距，同时避免三层图标径向堆叠。
      const angleOffsets = [-Math.PI / 5, Math.PI / 10, -Math.PI / 2];
      const angle = (layerIndex / layerCount) * Math.PI * 2 + angleOffsets[layer];
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle) * radius;
      const delay = (index * 0.22) + 's';
      return {
        '--x': x + 'px',
        '--y': y + 'px',
        animationDelay: delay,
      };
    };

    const freshnessText = computed(() => {
      if (!data.value?.generated_at) return "未知";
      const then = new Date(data.value.generated_at);
      const now = new Date();
      const hours = Math.floor((now - then) / 3600000);
      if (hours < 1) return "刚刚";
      if (hours < 24) return `${hours} 小时前`;
      return `${Math.floor(hours / 24)} 天前`;
    });

    const feedbackUrl = computed(() => {
      const base = "https://github.com/hangliuc/llm-price-compare/issues/new";
      const params = new URLSearchParams({
        template: "price-report.yml",
        labels: "price-error",
      });
      return `${base}?${params.toString()}`;
    });

    function toggleFilter(kind, value) {
      const arr = filters.value[kind];
      if (!arr) return;
      const i = arr.indexOf(value);
      if (i >= 0) arr.splice(i, 1);
      else arr.push(value);
    }

    function sortBy(key) {
      if (sortKey.value === key) sortAsc.value = !sortAsc.value;
      else { sortKey.value = key; sortAsc.value = true; }
    }

    function toggleExpand(id) {
      expanded.value = expanded.value === id ? null : id;
    }

    function billingLabel(b) {
      return { per_token: "Token", subscription: "订阅", coding_plan: "Coding Plan" }[b] || b;
    }

    const convertibleCurrencies = new Set(['CNY', 'USD']);
    const currencySymbols = { CNY: '¥', USD: '$', SGD: 'S$', EUR: '€', GBP: '£', JPY: '¥', INR: '₹' };

    // billing 路由下使用本币不换算；暂未配置汇率的币种在任何页面保持原币展示。
    function rowDisplayCurrency(row) {
      const originalCurrency = row.prices?.currency || 'CNY';
      if (routeName.value === 'billing' || !convertibleCurrencies.has(originalCurrency)) return originalCurrency;
      return displayCurrency.value;
    }

    function currencySymbol(row) {
      const cur = rowDisplayCurrency(row);
      return currencySymbols[cur] || `${cur} `;
    }

    function formatPrice(row, field) {
      const v = row.prices?.[field];
      if (v == null) return "—";
      const origCur = row.prices.currency;
      const dispCur = rowDisplayCurrency(row);
      let val = v;
      if (origCur !== dispCur) {
        if (origCur === "USD" && dispCur === "CNY") val = (v * USD_TO_CNY).toFixed(2);
        else if (origCur === "CNY" && dispCur === "USD") val = (v / USD_TO_CNY).toFixed(2);
      }
      const sym = currencySymbols[dispCur] || `${dispCur} `;
      // monthly_price 等非 token 计价字段不加 /1M
      if (field === 'monthly_price' || field === 'first_month_price') {
        return `${sym}${val}`;
      }
      return `${sym}${val} /1M`;
    }

    // 首页迷你价格预览在表头统一展示 /1M 单位，单元格仅保留金额。
    function formatPriceAmount(row, field) {
      const formatted = formatPrice(row, field);
      return formatted === '—' ? formatted : formatted.replace(' /1M', '');
    }

    // 上下文窗口格式化：128000 → 128K，2000000 → 2M
    function formatContext(ctx) {
      if (ctx == null) return '—';
      if (ctx >= 1000000) {
        const m = ctx / 1000000;
        return m % 1 === 0 ? `${m}M` : `${m.toFixed(1)}M`;
      }
      if (ctx >= 1000) {
        return `${Math.round(ctx / 1000)}K`;
      }
      return `${ctx}`;
    }

    // 月费格式化（coding_plan / subscription）
    function formatMonthly(row) {
      const p = row.prices;
      if (!p || p.monthly_price == null) return "—";
      const origCur = p.currency;
      const dispCur = rowDisplayCurrency(row);
      let val = p.monthly_price;
      if (origCur !== dispCur) {
        if (origCur === "USD" && dispCur === "CNY") val = (val * USD_TO_CNY).toFixed(0);
        else if (origCur === "CNY" && dispCur === "USD") val = (val / USD_TO_CNY).toFixed(2);
      }
      const sym = currencySymbols[dispCur] || `${dispCur} `;
      return `${sym}${val}`;
    }

    // 月费数字部分（符号由模板渲染，便于大字号排版）
    function formatMonthlyValue(row) {
      const p = row.prices;
      if (!p || p.monthly_price == null) return "—";
      const origCur = p.currency;
      const dispCur = rowDisplayCurrency(row);
      let val = p.monthly_price;
      if (origCur !== dispCur) {
        if (origCur === "USD" && dispCur === "CNY") val = (val * USD_TO_CNY).toFixed(0);
        else if (origCur === "CNY" && dispCur === "USD") val = (val / USD_TO_CNY).toFixed(2);
      }
      return Number.isInteger(Number(val)) ? String(val) : String(val);
    }

    // 额度格式化（coding_plan / subscription）
    function formatQuota(row) {
      const p = row.prices;
      if (!p) return "—";
      // 缺少结构化额度字段不代表无限使用；避免对套餐权益作无依据推断。
      if (p.included_quota == null) return "额度以官方说明为准";
      const q = p.included_quota;
      const unitText = {
        prompts_per_5h: "次/5小时",
        prompts_per_month: "次/月",
        calls_per_month: "次/月",
        base: "倍额度",
        credits_in_billions: "亿 credits",
        USD: "美元额度",
      }[p.quota_unit] || p.quota_unit || "";
      if (p.quota_unit === "base") return `${q} ${unitText}`;
      if (p.quota_unit === "USD") return `$${q} ${unitText}`;
      return `${q.toLocaleString()} ${unitText}`.trim();
    }

    // 能力评分（notes 字段为 JSON，含 OpenRouter benchmarks）
    function benchmarkText(row) {
      if (!row.notes) return null;
      try {
        const obj = typeof row.notes === 'string' ? JSON.parse(row.notes) : row.notes;
        const bm = obj.benchmarks || {};
        const parts = [];
        if (bm.intelligence_index != null) parts.push(`智力 ${bm.intelligence_index}`);
        if (bm.coding_index != null) parts.push(`编码 ${bm.coding_index}`);
        if (bm.agentic_index != null) parts.push(`Agent ${bm.agentic_index}`);
        return parts.length ? parts.join(' · ') : null;
      } catch {
        return null;
      }
    }

    // 纯文本备注（非 JSON 的 notes，如 AWS 区域说明）
    function textNote(row) {
      if (!row.notes) return null;
      if (typeof row.notes === 'string') {
        try { JSON.parse(row.notes); return null; } catch { return row.notes; }
      }
      return null;
    }

    function staleHours(row) {
      const last = row.status?.last_success_at;
      if (!last) return "?";
      const hours = Math.floor((Date.now() - new Date(last)) / 3600000);
      return hours;
    }

    async function loadData() {
      const failures = [];
      for (const path of DATA_PATHS) {
        try {
          const resp = await fetch(path, { cache: "no-cache" });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          data.value = catalogV3ToViewData(await resp.json());
          error.value = null;
          return;
        } catch (e) {
          failures.push(`${path}: ${e.message}`);
        }
      }
      error.value = failures.join('；');
    }

    onMounted(() => {
      loadData();
      document.addEventListener('click', closeHomeModelPicker);
      document.addEventListener('click', closePlansMenu);
    });
    onBeforeUnmount(() => {
      document.removeEventListener('click', closeHomeModelPicker);
      document.removeEventListener('click', closePlansMenu);
    });

    return {
      data, error, searchQuery, globalSearch, searchFocused, searchMatches, searchSuggestions, goProvider, searchSubmit, view, displayCurrency, expanded,
      plansMenuOpen, plansMenuActive, togglePlansMenu, openPlansMenuOnHover, closePlansMenuOnHover, openPlansMenuAndFocus, closePlansMenu, closePlansMenuOnFocusOut,
      homePlansMenuOpen, toggleHomePlansMenu, openHomePlansMenuAndFocus, closeHomePlansMenu, closeHomePlansMenuOnFocusOut,
      sortKey, sortAsc, filters, regions, billingTypes, modalities,
      route, routeName, billingRoute, providerRouteId, currentProvider,
      compareRows, compareSelectedRows, comparePickerRows, compareSelectedIds,
      compareProviderFilterList, compareModalities,
      compareContextFilter, comparePriceFilter, compareRegionFilter, compareSortOption,
      compareSearchQuery,
      compareProviderFilters, compareModalityFilters, toggleCompareProvider, toggleCompareModality,
      compareVisibleFields, compareFieldOptions, compareWorkspaceOpen, comparePickerIndex,
      comparePickerQuery, compareSelectionNotice, compareActiveFilterCount,
      isCompareSelected, toggleCompareSelection, removeCompareSelection, clearCompareSelection,
      startCompareWorkspace, openComparePicker, selectCompareReplacement, closeComparePicker,
      closeCompareWorkspace,
      clearCompareFilters, toggleCompareField, isCompareLowest,
      catalogRows, catalogPageRows, catalogTotalModels, catalogProviderCount, catalogTotalPages,
      catalogPageNumbers, catalogPage, catalogPageSize, catalogActiveFilterCount, catalogSortLabel,
      catalogContextFilter, catalogRegionFilter, catalogQuickFilter, catalogSortOption,
      catalogSearchQuery,
      catalogProviderFilters, catalogModalityFilters, toggleCatalogProvider, toggleCatalogModality,
      catalogVisibleFields, catalogFieldOptions, clearCatalogFilters, toggleCatalogField,
      sortCatalogBy, catalogSortIndicator, goToCompareWorkspace,
      plansSearchQuery, plansProviderFilters, plansPriceKindFilter, plansPriceRangeFilter,
      plansQuotaTypeFilter, plansSortOption, plansGroupMode, plansExpandedIds, plansCompareOpen,
      plansSelectionNotice, plansBaseRows, plansProviderCount, plansProviderOptions,
      plansQuotaTypeOptions, plansRows, plansGroups, currentPlansVisibleFields,
      currentPlanSelectedRows, plansActiveFilterCount, plansSortLabel,
      togglePlansProvider, clearPlansFilters, togglePlansField, setPlansSortOption, setPlansGroupMode, togglePlanExpanded,
      isPlanSelected, togglePlanSelection, removePlanSelection, clearPlanSelection,
      openPlansCompare, closePlansCompare, formatPlanPrice, formatPlanQuota,
      filteredRows, homePreviewRows, homeCompareRows, homeCompareCandidates, homeModelPickerIndex, homeModelPickerQuery, homeModelPickerRows, isHomeCompareLowest,
      openHomeModelPicker, selectHomeCompareModel, addHomePreviewToCompare, closeHomeModelPicker, handleHomeModelPickerKeydown,
      homePlanRows, currentRow, totalProducts, staleCount, successCount, freshnessText,
      perTokenCount, subscriptionCount, codingPlanCount, plansCount,
      codingIDEs: CODING_IDES, codingIDERows: CODING_IDE_ROWS,
      billingSlides, billingSlideIndex, billingSlideDir, goBillingSlide,
      tickerFeatured, tickerCards,
      providerList, homeProviderList, providerFilterList, providerSearch, providerListByRegion, groupedRows, billingFlatProducts, allProvidersForOrbit, orbitStyle,
      providerPerTokenRows, providerPlanGroups,
      providerBillingTabs, providerBillingTab, providerCurrentRows,
      displayRows, billingCardGroups, billingCurrencyTab, billingCnyCount, billingUsdCount,
      feedbackUrl, toggleFilter, sortBy, toggleExpand, billingLabel, billingLabelShort,
      formatPrice, formatPriceAmount, formatContext, formatMonthly, formatMonthlyValue, formatQuota, benchmarkText, textNote, staleHours, iconUrl, onIconError, goHash, currencySymbol,
    };
  },
}).mount("#app");
