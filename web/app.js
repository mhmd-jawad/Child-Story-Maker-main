const CONFIG = window.APP_CONFIG || {};
const API_BASE = CONFIG.apiBase || "";
const SUPABASE_URL = CONFIG.supabaseUrl || "";
const SUPABASE_ANON_KEY = CONFIG.supabaseAnonKey || "";
const USE_SUPABASE = Boolean(
  SUPABASE_URL &&
    SUPABASE_ANON_KEY &&
    window.supabase &&
    typeof window.supabase.createClient === "function"
);
const supabaseClient = USE_SUPABASE
  ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;
const TOKEN_KEY = "cs_token";
const ACTIVE_CHILD_KEY = "cs_active_child";

const state = {
  token: localStorage.getItem(TOKEN_KEY) || "",
  userEmail: "",
  children: [],
  activeChildId: localStorage.getItem(ACTIVE_CHILD_KEY) || null,
  story: null,
};

const authView = document.getElementById("authView");
const childView = document.getElementById("childView");
const studioView = document.getElementById("studioView");
const userBadge = document.getElementById("userBadge");
const logoutBtn = document.getElementById("logoutBtn");
const profilesBtn = document.getElementById("profilesBtn");
const childGrid = document.getElementById("childGrid");
const childForm = document.getElementById("childForm");
const toStudioBtn = document.getElementById("toStudioBtn");
const activeChildBadge = document.getElementById("activeChildBadge");
const storyForm = document.getElementById("storyForm");
const storyOutput = document.getElementById("storyOutput");
const storyStatus = document.getElementById("storyStatus");
const downloadZipBtn = document.getElementById("downloadZipBtn");
const downloadPdfBtn = document.getElementById("downloadPdfBtn");
const regenImagesBtn = document.getElementById("regenImagesBtn");
const chaptersValue = document.getElementById("chaptersValue");
const toast = document.getElementById("toast");

function apiUrl(path) {
  if (!API_BASE) return path;
  const base = API_BASE.endsWith("/") ? API_BASE.slice(0, -1) : API_BASE;
  return `${base}${path}`;
}

function childIdEquals(left, right) {
  return String(left) === String(right);
}

const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const tabs = document.querySelectorAll(".tab");

function showToast(message, tone = "dark") {
  toast.textContent = message;
  toast.classList.remove("hidden");
  toast.style.background = tone === "error" ? "#b91c1c" : "#1f2937";
  setTimeout(() => toast.classList.add("hidden"), 2400);
}

function setView(view) {
  [authView, childView, studioView].forEach((el) => el.classList.add("hidden"));
  view.classList.remove("hidden");
}

function setAuthUI(loggedIn) {
  if (loggedIn) {
    userBadge.classList.remove("hidden");
    logoutBtn.classList.remove("hidden");
    profilesBtn.classList.remove("hidden");
  } else {
    userBadge.classList.add("hidden");
    logoutBtn.classList.add("hidden");
    profilesBtn.classList.add("hidden");
  }
}

async function bearerToken() {
  if (USE_SUPABASE) {
    const { data, error } = await supabaseClient.auth.getSession();
    if (error) return "";
    return data.session?.access_token || "";
  }
  return state.token || "";
}

async function authHeaders({ json = true } = {}) {
  const headers = {};
  if (json) headers["Content-Type"] = "application/json";
  const token = await bearerToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function api(path, options = {}) {
  const headers = {
    ...(await authHeaders({ json: true })),
    ...(options.headers || {}),
  };
  const resp = await fetch(apiUrl(path), {
    headers,
    ...options,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = data.detail || JSON.stringify(data);
    } catch (err) {
      // ignore
    }
    throw new Error(detail);
  }
  const contentType = resp.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return resp.json();
  }
  return null;
}

async function loadSession() {
  if (USE_SUPABASE) {
    try {
      const { data, error } = await supabaseClient.auth.getUser();
      if (error || !data.user) {
        setAuthUI(false);
        setView(authView);
        return;
      }
      state.userEmail = data.user.email || "";
      userBadge.textContent = state.userEmail;
      setAuthUI(true);
      await loadChildren();
    } catch (err) {
      setAuthUI(false);
      setView(authView);
    }
    return;
  }
  if (!state.token) {
    setAuthUI(false);
    setView(authView);
    return;
  }
  try {
    const me = await api("/auth/me");
    state.userEmail = me.email;
    userBadge.textContent = me.email;
    setAuthUI(true);
    await loadChildren();
  } catch (err) {
    state.token = "";
    localStorage.removeItem(TOKEN_KEY);
    setAuthUI(false);
    setView(authView);
  }
}

async function loadChildren() {
  if (USE_SUPABASE) {
    const { data, error } = await supabaseClient
      .from("children")
      .select("id, name, age, interests")
      .order("created_at", { ascending: true });
    if (error) {
      throw new Error(error.message);
    }
    state.children = data || [];
  } else {
    const data = await api("/children");
    state.children = data.children || [];
  }
  renderChildren();
  if (state.children.length === 0) {
    setView(childView);
  } else {
    if (!state.activeChildId) {
      state.activeChildId = String(state.children[0].id);
      localStorage.setItem(ACTIVE_CHILD_KEY, state.activeChildId);
    }
    setView(studioView);
    renderActiveChild();
  }
}

function renderChildren() {
  childGrid.innerHTML = "";
  if (state.children.length === 0) {
    childGrid.innerHTML = "<div class='child-card'>No child profiles yet.</div>";
    toStudioBtn.classList.add("hidden");
    return;
  }
  toStudioBtn.classList.remove("hidden");
  state.children.forEach((child) => {
    const card = document.createElement("div");
    card.className = "child-card";
    card.innerHTML = `
      <h4>${child.name}</h4>
      <div class="chip">Age ${child.age}</div>
      <p>${child.interests}</p>
      <button class="ghost" data-action="select">Use this child</button>
      <button class="ghost" data-action="delete">Delete</button>
    `;
    card.querySelector('[data-action="select"]').addEventListener("click", () => {
      state.activeChildId = String(child.id);
      localStorage.setItem(ACTIVE_CHILD_KEY, state.activeChildId);
      setView(studioView);
      renderActiveChild();
    });
    card.querySelector('[data-action="delete"]').addEventListener("click", async () => {
      if (!confirm(`Delete ${child.name}?`)) return;
      try {
        if (USE_SUPABASE) {
          const { error } = await supabaseClient
            .from("children")
            .delete()
            .eq("id", child.id);
          if (error) {
            throw new Error(error.message);
          }
        } else {
          await api(`/children/${child.id}`, { method: "DELETE" });
        }
        await loadChildren();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
    childGrid.appendChild(card);
  });
}

function renderActiveChild() {
  const child = state.children.find((c) => childIdEquals(c.id, state.activeChildId));
  if (!child) {
    activeChildBadge.textContent = "No active child";
    return;
  }
  activeChildBadge.textContent = `${child.name}, age ${child.age}`;
}

function ageToGroup(age) {
  if (age <= 5) return "3-5 (Pre-K)";
  if (age <= 8) return "6-8 (Grades 1-3)";
  return "9-12 (Middle)";
}

function getActiveChild() {
  return state.children.find((c) => childIdEquals(c.id, state.activeChildId));
}

function buildPrompt(basePrompt, child, traits, setting) {
  const parts = [];
  if (child) {
    parts.push(`Main character: ${child.name}`);
    parts.push(`Themes: ${child.interests}`);
    parts.push(`Child age: ${child.age}`);
  }
  if (traits) parts.push(`Character traits: ${traits}`);
  if (setting) parts.push(`Setting: ${setting}`);
  if (parts.length === 0) return basePrompt;
  return `${basePrompt}\n\nPersonalization:\n- ${parts.join("\n- ")}`;
}

function updateChaptersValue() {
  const chapters = storyForm.elements["chapters"].value;
  chaptersValue.textContent = chapters;
}

async function generateStory(payload) {
  storyStatus.textContent = "Generating story...";
  storyOutput.innerHTML = "";
  downloadZipBtn.classList.add("hidden");
  downloadPdfBtn.classList.add("hidden");
  regenImagesBtn.classList.add("hidden");

  const story = await api("/story", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.story = story;
  renderStory(story);
}

async function generateImagesPerSection(storyId, size, imageStyle) {
  if (!state.story) return;
  const sections = state.story.sections || [];
  if (sections.length === 0) return;
  for (let i = 0; i < sections.length; i += 1) {
    const section = sections[i];
    if (section.image_url) continue;
    storyStatus.textContent = `Generating images (${i + 1}/${sections.length})...`;
    const updated = await api(`/story/${storyId}/sections/${section.id}/image`, {
      method: "POST",
      body: JSON.stringify({ size, image_style: imageStyle }),
    });
    const idx = state.story.sections.findIndex((s) => s.id === updated.id);
    if (idx >= 0) {
      state.story.sections[idx] = { ...state.story.sections[idx], ...updated };
    }
    renderStory(state.story);
  }
  storyStatus.textContent = state.story.title || "Story";
}

function renderStory(story) {
  if (!story) return;
  storyStatus.textContent = story.title || "Story";
  storyOutput.innerHTML = "";
  (story.sections || []).forEach((section) => {
    const card = document.createElement("div");
    card.className = "story-section";
    let imgUrl = "";
    if (section.image_url) {
      imgUrl = section.image_url.startsWith("http")
        ? section.image_url
        : new URL(section.image_url, window.location.origin).toString();
    }
    card.innerHTML = `
      <h4>${section.title || "Section"}</h4>
      <p>${section.text.replace(/\n/g, "<br />")}</p>
      ${imgUrl ? `<img src="${imgUrl}" alt="Story art" />` : ""}
    `;
    storyOutput.appendChild(card);
  });

  downloadZipBtn.classList.remove("hidden");
  downloadPdfBtn.classList.remove("hidden");
  if (story.sections && story.sections.some((s) => !s.image_url)) {
    regenImagesBtn.classList.remove("hidden");
  }
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    if (tab.dataset.tab === "login") {
      loginForm.classList.remove("hidden");
      registerForm.classList.add("hidden");
    } else {
      registerForm.classList.remove("hidden");
      loginForm.classList.add("hidden");
    }
  });
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(loginForm);
  const email = String(formData.get("email") || "").trim();
  const password = String(formData.get("password") || "");
  try {
    if (USE_SUPABASE) {
      const { data, error } = await supabaseClient.auth.signInWithPassword({
        email,
        password,
      });
      if (error) {
        throw new Error(error.message);
      }
      state.userEmail = data.user?.email || email;
      userBadge.textContent = state.userEmail;
      setAuthUI(true);
      await loadChildren();
      return;
    }

    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
      }),
    });
    state.token = data.token;
    state.userEmail = data.email;
    localStorage.setItem(TOKEN_KEY, data.token);
    userBadge.textContent = data.email;
    setAuthUI(true);
    await loadChildren();
  } catch (err) {
    showToast(err.message, "error");
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(registerForm);
  const email = String(formData.get("email") || "").trim();
  const password = String(formData.get("password") || "");
  try {
    if (USE_SUPABASE) {
      const { data, error } = await supabaseClient.auth.signUp({
        email,
        password,
      });
      if (error) {
        throw new Error(error.message);
      }
      if (!data.session) {
        showToast("Check your email to confirm your account.");
        return;
      }
      state.userEmail = data.user?.email || email;
      userBadge.textContent = state.userEmail;
      setAuthUI(true);
      await loadChildren();
      return;
    }

    const data = await api("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
      }),
    });
    state.token = data.token;
    state.userEmail = data.email;
    localStorage.setItem(TOKEN_KEY, data.token);
    userBadge.textContent = data.email;
    setAuthUI(true);
    await loadChildren();
  } catch (err) {
    showToast(err.message, "error");
  }
});

childForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(childForm);
  try {
    const payload = {
      name: formData.get("name"),
      age: Number(formData.get("age")),
      interests: formData.get("interests"),
    };
    if (USE_SUPABASE) {
      const { error } = await supabaseClient.from("children").insert(payload);
      if (error) {
        throw new Error(error.message);
      }
      childForm.reset();
      await loadChildren();
      return;
    }

    await api("/children", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    childForm.reset();
    await loadChildren();
  } catch (err) {
    showToast(err.message, "error");
  }
});

storyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const child = getActiveChild();
  if (!child) {
    showToast("Select a child profile first.", "error");
    return;
  }

  const formData = new FormData(storyForm);
  const basePrompt = formData.get("prompt");
  const traits = formData.get("traits");
  const setting = formData.get("setting");
  const wantImages = Boolean(formData.get("generate_images"));

  const payload = {
    prompt: buildPrompt(basePrompt, child, traits, setting),
    sections: Number(formData.get("chapters")),
    age: ageToGroup(child.age),
    language: formData.get("language"),
    style: formData.get("style"),
    title: formData.get("title") || "",
    child_id: String(child.id),
    generate_images: false,
    image_style: formData.get("image_style"),
    image_size: "512x512",
  };

  try {
    await generateStory(payload);
    if (wantImages && state.story?.story_id) {
      await generateImagesPerSection(
        state.story.story_id,
        payload.image_size,
        payload.image_style
      );
    }
  } catch (err) {
    storyStatus.textContent = "Story failed to generate.";
    showToast(err.message, "error");
  }
});

async function downloadFile(path, fallbackName) {
  if (!state.story) return;
  try {
    const resp = await fetch(apiUrl(path), {
      headers: await authHeaders({ json: false }),
    });
    if (!resp.ok) {
      throw new Error("Download failed.");
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fallbackName;
    link.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    showToast(err.message, "error");
  }
}

downloadZipBtn.addEventListener("click", () => {
  if (!state.story) return;
  downloadFile(`/story/${state.story.story_id}/export/zip`, "story.zip");
});

downloadPdfBtn.addEventListener("click", () => {
  if (!state.story) return;
  downloadFile(`/story/${state.story.story_id}/export/pdf`, "story.pdf");
});

regenImagesBtn.addEventListener("click", async () => {
  if (!state.story) return;
  try {
    const imageStyle = storyForm.elements["image_style"].value || "Watercolor";
    await generateImagesPerSection(state.story.story_id, "512x512", imageStyle);
  } catch (err) {
    showToast(err.message, "error");
  }
});

logoutBtn.addEventListener("click", async () => {
  try {
    if (USE_SUPABASE) {
      await supabaseClient.auth.signOut();
    } else {
      await api("/auth/logout", { method: "POST" });
    }
  } catch (err) {
    // ignore
  }
  state.token = "";
  state.userEmail = "";
  state.children = [];
  state.activeChildId = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ACTIVE_CHILD_KEY);
  setAuthUI(false);
  setView(authView);
});

profilesBtn.addEventListener("click", () => {
  renderChildren();
  setView(childView);
});

toStudioBtn.addEventListener("click", () => {
  setView(studioView);
});

storyForm.elements["chapters"].addEventListener("input", updateChaptersValue);
updateChaptersValue();

loadSession();
