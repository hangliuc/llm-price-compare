const { createApp, ref, computed, onMounted } = Vue;

const USD_TO_CNY = 7.2;  // MVP 硬编码汇率

// 本地 /ui/ 路径用 ../data/，GitHub Pages 根路径用 data/
const DATA_PATH = window.location.pathname.includes("/ui/") ? "../data/prices.json" : "data/prices.json";

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
    const filters = ref({
      region: [],
      billing: [],
      modality: [],
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
      filteredRows, currentRow, totalProducts, staleCount, freshnessText,
      feedbackUrl, toggleFilter, sortBy, toggleExpand, billingLabel,
      formatPrice, staleHours,
    };
  },
}).mount("#app");
