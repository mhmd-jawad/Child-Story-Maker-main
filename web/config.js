window.APP_CONFIG = {
  apiBase:
    window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
      ? ""
      : "/api",
  supabaseUrl: "https://dvepmilzidmzizorkerk.supabase.co",
  supabaseAnonKey: "sb_publishable_AYcy4137ckZhxLiApJucoQ_FSvUT1W_"
};
