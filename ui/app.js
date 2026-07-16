const { createApp, ref, computed, onMounted, watch } = Vue;

const USD_TO_CNY = 7.2;  // MVP 硬编码汇率

// 本地 /ui/ 路径用 ../data/，GitHub Pages 根路径用 data/
const inUiDir = window.location.pathname.includes("/ui/");
const DATA_PATH = inUiDir ? "../data/prices.json" : "data/prices.json";

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
};
const PNG_ICONS = ['volcengine'];
const iconUrl = (id) => {
  const name = ICON_FILES[id] || id;
  const ext = PNG_ICONS.includes(id) ? 'png' : 'svg';
  return inUiDir ? `icons/${name}.${ext}` : `ui/icons/${name}.${ext}`;
};

// 厂商品牌色（图标加载失败时用作占位背景）
const PROVIDER_COLORS = {
  openai: '#10A37F', anthropic: '#191919', zhipu: '#4B6BFF', volcengine: '#0B8CE6',
  deepseek: '#5786FE', opencode: '#1a1a1a', google: '#4285F4',
  qwen: '#6950EF', moonshot: '#000000',
  aws: '#FF9900', minimax: '#FF6B6B', xiaomi: '#FF6900',
  githubcopilot: '#24292E', cursor: '#000000',
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
};

createApp({
  setup() {
    const data = ref(null);
    const error = ref(null);
    const searchQuery = ref("");
    // 全局导航搜索（首页/比较页共用）：输入厂商中英文名/ID 模糊匹配，下拉建议跳转
    const globalSearch = ref("");
    const searchFocused = ref(false);
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
        if (!seen.has(p.id)) {
          seen.add(p.id);
          result.push(p);
        }
      }
      // 再加 provider_status 里有但 providers 里没有的（抓取失败的厂商）
      for (const s of (data.value.provider_status || [])) {
        const pid = s.provider_id;
        if (!seen.has(pid)) {
          seen.add(pid);
          const meta = PROVIDER_META[pid] || { name: pid, name_en: pid, region: 'cn' };
          result.push({ id: pid, ...meta });
        }
      }
      // 最后加 PROVIDER_META 中定义但尚未出现在数据中的厂商（新增厂商，尚无适配器）
      for (const [pid, meta] of Object.entries(PROVIDER_META)) {
        if (!seen.has(pid)) {
          seen.add(pid);
          result.push({ id: pid, ...meta });
        }
      }
      return result;
    });

    // 图标加载失败时用品牌色+首字母占位
    function onIconError(e, providerId) {
      const name = (data.value?.providers.find(p => p.id === providerId)?.name) || providerId;
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
    // 三种计费方式的产品数量
    const perTokenCount = computed(() =>
      allRows.value.filter(r => r.billing_type === 'per_token' && !r.stale).length
    );
    const subscriptionCount = computed(() =>
      allRows.value.filter(r => r.billing_type === 'subscription' && !r.stale).length
    );
    const codingPlanCount = computed(() =>
      allRows.value.filter(r => r.billing_type === 'coding_plan' && !r.stale).length
    );

    // 首页「三种计费方式」编辑杂志式轮播
    const billingSlides = computed(() => [
      {
        index: '01',
        label: 'Per Token',
        name: '按需计费',
        desc: '按实际 Token 用量计费，输入输出分别定价，适合低频或弹性调用',
        count: perTokenCount.value,
        href: '#/billing/per_token',
        image: 'image/Pay as you go.png',
        cta: '查看价格',
      },
      {
        index: '02',
        label: 'Subscription',
        name: '订阅制',
        desc: '面向终端用户的产品订阅，固定月费换不限量使用，代表 ChatGPT Plus、Claude Pro',
        count: subscriptionCount.value,
        href: '#/billing/subscription',
        image: 'image/Subscribe.png',
        cta: '查看套餐',
      },
      {
        index: '03',
        label: 'Coding Plan',
        name: '编程套餐',
        desc: '面向开发者的 API 额度套餐，月付换 Token 池，代表 GLM Coding、方舟 Coding Plan',
        count: codingPlanCount.value,
        href: '#/billing/coding_plan',
        image: 'image/coding plan.png',
        cta: '查看套餐',
      },
    ]);
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

    // 首页「最新价格一览」预览：按模型发布时间倒序，仅 per_token，去重，取 8 条
    const homePreviewRows = computed(() => {
      const rows = allRows.value.filter(r =>
        r.billing_type === 'per_token' && !r.stale && r.prices && r.prices.input != null
      );
      // 同一 model 取最新 release_date 的一条
      const byModel = new Map();
      for (const r of rows) {
        const key = r.model || r.id;
        const prev = byModel.get(key);
        if (!prev) {
          byModel.set(key, r);
        } else {
          const a = prev.release_date || '';
          const b = r.release_date || '';
          if (b > a) byModel.set(key, r);
        }
      }
      const deduped = [...byModel.values()];
      // 按 release_date 倒序（null 排到最后）
      deduped.sort((a, b) => {
        const da = a.release_date || '';
        const db = b.release_date || '';
        if (!da && !db) return 0;
        if (!da) return 1;
        if (!db) return -1;
        return db.localeCompare(da);
      });
      return deduped.slice(0, 8);
    });

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
    // 分 3 层环：内环 3 个、中环 3 个、外环 3 个（共 9 个）
    const orbitStyle = (index, total) => {
      let layer, layerCount, layerIndex;
      if (index < 3) {
        layer = 0; layerCount = 3; layerIndex = index;
      } else if (index < 6) {
        layer = 1; layerCount = 3; layerIndex = index - 3;
      } else {
        layer = 2; layerCount = total - 6; layerIndex = index - 6;
      }
      const radii = [95, 150, 205];
      const radius = radii[layer];
      // 每层错开角度，避免图标径向对齐
      const angle = (layerIndex / layerCount) * Math.PI * 2 + (layer * 0.5);
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

    function formatPrice(row, field) {
      const v = row.prices?.[field];
      if (v == null) return "—";
      const cur = row.prices.currency;
      let val;
      if (cur === displayCurrency.value) {
        val = v;
      } else if (cur === "USD" && displayCurrency.value === "CNY") {
        val = (v * USD_TO_CNY).toFixed(2);
      } else if (cur === "CNY" && displayCurrency.value === "USD") {
        val = (v / USD_TO_CNY).toFixed(2);
      } else {
        val = v;
      }
      const sym = displayCurrency.value === "CNY" ? "¥" : "$";
      // monthly_price 等非 token 计价字段不加 /1M
      if (field === 'monthly_price' || field === 'first_month_price') {
        return `${sym}${val}`;
      }
      return `${sym}${val} /1M`;
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
      const cur = p.currency;
      let val = p.monthly_price;
      const sym = displayCurrency.value === "CNY" ? "¥" : "$";
      if (cur === displayCurrency.value) {
        val = val;
      } else if (cur === "USD" && displayCurrency.value === "CNY") {
        val = (val * USD_TO_CNY).toFixed(0);
      } else if (cur === "CNY" && displayCurrency.value === "USD") {
        val = (val / USD_TO_CNY).toFixed(2);
      }
      return `${sym}${val}`;
    }

    // 月费数字部分（符号由模板渲染，便于大字号排版）
    function formatMonthlyValue(row) {
      const p = row.prices;
      if (!p || p.monthly_price == null) return "—";
      const cur = p.currency;
      let val = p.monthly_price;
      if (cur === displayCurrency.value) {
        val = val;
      } else if (cur === "USD" && displayCurrency.value === "CNY") {
        val = (val * USD_TO_CNY).toFixed(0);
      } else if (cur === "CNY" && displayCurrency.value === "USD") {
        val = (val / USD_TO_CNY).toFixed(2);
      }
      // 整数不带小数
      return Number.isInteger(Number(val)) ? String(val) : String(val);
    }

    // 额度格式化（coding_plan / subscription）
    function formatQuota(row) {
      const p = row.prices;
      if (!p) return "—";
      if (p.included_quota == null) return "不限量";
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

    function staleHours(row) {
      const last = row.status?.last_success_at;
      if (!last) return "?";
      const hours = Math.floor((Date.now() - new Date(last)) / 3600000);
      return hours;
    }

    async function loadData() {
      try {
        const resp = await fetch(DATA_PATH, { cache: "no-cache" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        data.value = await resp.json();
      } catch (e) {
        error.value = e.message;
      }
    }

    onMounted(loadData);

    return {
      data, error, searchQuery, globalSearch, searchFocused, searchMatches, searchSuggestions, goProvider, searchSubmit, view, displayCurrency, expanded,
      sortKey, sortAsc, filters, regions, billingTypes, modalities,
      route, routeName, billingRoute, providerRouteId, currentProvider,
      filteredRows, homePreviewRows, currentRow, totalProducts, staleCount, successCount, freshnessText,
      perTokenCount, subscriptionCount, codingPlanCount,
      billingSlides, billingSlideIndex, billingSlideDir, goBillingSlide,
      tickerFeatured, tickerCards,
      providerList, providerFilterList, providerSearch, providerListByRegion, groupedRows, billingFlatProducts, allProvidersForOrbit, orbitStyle,
      providerPerTokenRows, providerPlanGroups,
      providerBillingTabs, providerBillingTab, providerCurrentRows,
      feedbackUrl, toggleFilter, sortBy, toggleExpand, billingLabel, billingLabelShort,
      formatPrice, formatContext, formatMonthly, formatMonthlyValue, formatQuota, benchmarkText, staleHours, iconUrl, onIconError, goHash,
    };
  },
}).mount("#app");
