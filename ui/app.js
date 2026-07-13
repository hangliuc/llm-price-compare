const { createApp, ref, computed, onMounted } = Vue;

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
  moonshot: { name: '月之暗面', name_en: 'Moonshot AI', region: 'cn' },
  aws: { name: 'AWS', name_en: 'Amazon Web Services', region: 'us' },
  minimax: { name: 'MiniMax', name_en: 'MiniMax', region: 'cn' },
  xiaomi: { name: '小米', name_en: 'Xiaomi', region: 'cn' },
};

createApp({
  setup() {
    const data = ref(null);
    const error = ref(null);
    const searchQuery = ref("");
    const view = ref("table");
    const displayCurrency = ref("CNY");
    const expanded = ref(null);
    const sortKey = ref("inputPrice");
    const sortAsc = ref(true);
    const route = ref(window.location.hash || "#/");
    const filters = ref({
      region: [],
      billing: [],
      modality: [],
    });

    // 监听 hash 变化
    window.addEventListener("hashchange", () => {
      route.value = window.location.hash || "#/";
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
      return "home";
    });

    // 计费类型路由（按需计费 / 订阅制 / Coding Plan）
    const billingRoute = computed(() => {
      if (routeName.value !== "billing") return null;
      return route.value.replace("#/billing/", "");
    });

    const regions = ["cn", "us", "eu"];
    const billingTypes = ["per_token", "subscription", "coding_plan"];
    const modalities = ["text", "vision", "audio"];

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
          return sortAsc.value ? va.localeCompare(vb) : vb.localeCompare(va);
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
        return {
          ...p,
          productCount: (p.products || []).length,
          stale: status.stale === true,
          statusText: status.status === "ok" ? "正常" : (status.stale ? "数据过期" : "抓取失败"),
          statusOk: status.status === "ok",
        };
      });
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
      if (key === "inputPrice") return row.prices?.input;
      if (key === "outputPrice") return row.prices?.output;
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
      const base = "https://github.com/llm-price-compare/llm-price-compare/issues/new";
      const params = new URLSearchParams({
        template: "price-report.yml",
        labels: "price-error",
      });
      return `${base}?${params.toString()}`;
    });

    function toggleFilter(kind, value) {
      const arr = filters.value[kind === "region" ? "region" : (kind === "billing" ? "billing" : "modality")];
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
      if (cur === displayCurrency.value) {
        return displayCurrency.value === "CNY" ? `¥${v}` : `$${v}`;
      }
      // 换算
      if (cur === "USD" && displayCurrency.value === "CNY") {
        return `¥${(v * USD_TO_CNY).toFixed(2)}`;
      }
      if (cur === "CNY" && displayCurrency.value === "USD") {
        return `$${(v / USD_TO_CNY).toFixed(2)}`;
      }
      return v;
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
      data, error, searchQuery, view, displayCurrency, expanded,
      sortKey, sortAsc, filters, regions, billingTypes, modalities,
      route, routeName, billingRoute,
      filteredRows, currentRow, totalProducts, staleCount, successCount, freshnessText,
      tickerFeatured, tickerCards,
      providerList, allProvidersForOrbit, orbitStyle,
      feedbackUrl, toggleFilter, sortBy, toggleExpand, billingLabel,
      formatPrice, staleHours, iconUrl, onIconError, goHash,
    };
  },
}).mount("#app");
