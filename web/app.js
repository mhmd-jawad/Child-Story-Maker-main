const CONFIG = window.APP_CONFIG || {};
const API_BASE =
  CONFIG.apiBase ||
  (window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1"
    ? ""
    : "/api");
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
  stories: [],
  report: null,
  learning: null,
  shareToken: "",
  shareStory: null,
};

const authView = document.getElementById("authView");
const childView = document.getElementById("childView");
const libraryView = document.getElementById("libraryView");
const studioView = document.getElementById("studioView");
const shareView = document.getElementById("shareView");
const userBadge = document.getElementById("userBadge");
const logoutBtn = document.getElementById("logoutBtn");
const profilesBtn = document.getElementById("profilesBtn");
const libraryBtn = document.getElementById("libraryBtn");
const studioBtn = document.getElementById("studioBtn");
const childGrid = document.getElementById("childGrid");
const childForm = document.getElementById("childForm");
const toStudioBtn = document.getElementById("toStudioBtn");
const activeChildBadge = document.getElementById("activeChildBadge");
const storyForm = document.getElementById("storyForm");
const storyPanel = document.getElementById("storyPanel");
const reportPanel = document.getElementById("reportPanel");
const reportBody = document.getElementById("reportBody");
const learningPanel = document.getElementById("learningPanel");
const learningBody = document.getElementById("learningBody");
const learningGenerateBtn = document.getElementById("learningGenerateBtn");
const storyStatus = document.getElementById("storyStatus");
const downloadZipBtn = document.getElementById("downloadZipBtn");
const downloadPdfBtn = document.getElementById("downloadPdfBtn");
const shareBtn = document.getElementById("shareBtn");
const regenImagesBtn = document.getElementById("regenImagesBtn");
const chaptersValue = document.getElementById("chaptersValue");
const toast = document.getElementById("toast");
const libraryGrid = document.getElementById("libraryGrid");
const newStoryBtn = document.getElementById("newStoryBtn");
const shareOutput = document.getElementById("shareOutput");
const shareDownloadZipBtn = document.getElementById("shareDownloadZipBtn");
const shareDownloadPdfBtn = document.getElementById("shareDownloadPdfBtn");
const openAppBtn = document.getElementById("openAppBtn");
const storyTabs = document.querySelectorAll(".story-tab");
const ttsBtn = document.getElementById("ttsBtn");
const playAllBtn = document.getElementById("playAllBtn");
const voiceSelect = document.getElementById("voiceSelect");

const audioPlayer = new Audio();
let audioQueue = [];

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
  [authView, childView, libraryView, studioView, shareView].forEach((el) =>
    el.classList.add("hidden")
  );
  view.classList.remove("hidden");
}

function setAuthUI(loggedIn) {
  if (loggedIn) {
    userBadge.classList.remove("hidden");
    logoutBtn.classList.remove("hidden");
    profilesBtn.classList.remove("hidden");
    libraryBtn.classList.remove("hidden");
    studioBtn.classList.remove("hidden");
  } else {
    userBadge.classList.add("hidden");
    logoutBtn.classList.add("hidden");
    profilesBtn.classList.add("hidden");
    libraryBtn.classList.add("hidden");
    studioBtn.classList.add("hidden");
  }
}

function setStoryTab(tabName) {
  storyTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === tabName);
  });
  storyPanel.classList.toggle("hidden", tabName !== "story");
  reportPanel.classList.toggle("hidden", tabName !== "report");
  learningPanel.classList.toggle("hidden", tabName !== "learning");
}

function resetStoryPanels() {
  reportBody.innerHTML = "";
  learningBody.innerHTML = "";
  state.report = null;
  state.learning = null;
  setStoryTab("story");
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
      await loadLibrary();
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
    await loadLibrary();
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
  storyPanel.innerHTML = "";
  reportBody.innerHTML = "";
  learningBody.innerHTML = "";
  downloadZipBtn.classList.add("hidden");
  downloadPdfBtn.classList.add("hidden");
  shareBtn.classList.add("hidden");
  regenImagesBtn.classList.add("hidden");
  playAllBtn.classList.add("hidden");

  const story = await api("/story", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.story = story;
  renderStory(story);
  loadLibrary();
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
  resetStoryPanels();
  storyStatus.textContent = story.title || "Story";
  renderStorySections(story, storyPanel);

  downloadZipBtn.classList.remove("hidden");
  downloadPdfBtn.classList.remove("hidden");
  shareBtn.classList.remove("hidden");
  if (story.sections && story.sections.some((s) => !s.image_url)) {
    regenImagesBtn.classList.remove("hidden");
  }
  if (story.sections && story.sections.some((s) => s.audio_url)) {
    playAllBtn.classList.remove("hidden");
  } else {
    playAllBtn.classList.add("hidden");
  }
}

function renderStorySections(story, targetEl) {
  targetEl.innerHTML = "";
  (story.sections || []).forEach((section) => {
    const card = document.createElement("div");
    card.className = "story-section";
    const imgUrl = normalizeMediaUrl(section.image_url);
    const audioUrl = normalizeMediaUrl(section.audio_url);
    card.innerHTML = `
      <h4>${section.title || "Section"}</h4>
      <p>${section.text.replace(/\n/g, "<br />")}</p>
      ${audioUrl ? `<button class="listen-btn" data-audio="${audioUrl}"><span>🔊</span> Listen</button>` : ""}
      ${imgUrl ? `<img src="${imgUrl}" alt="Story art" />` : ""}
    `;
    const listenBtn = card.querySelector(".listen-btn");
    if (listenBtn) {
      listenBtn.addEventListener("click", () => {
        playAudio(audioUrl);
      });
    }
    targetEl.appendChild(card);
  });
}

function normalizeMediaUrl(url) {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  return new URL(url, window.location.origin).toString();
}

function playAudio(url) {
  if (!url) return;
  audioQueue = [];
  audioPlayer.src = url;
  audioPlayer.play().catch(() => {
    showToast("Unable to play audio.", "error");
  });
}

function playQueue(urls) {
  audioQueue = urls.slice();
  const next = audioQueue.shift();
  if (next) {
    audioPlayer.src = next;
    audioPlayer.play().catch(() => {
      showToast("Unable to play audio.", "error");
    });
  }
}

audioPlayer.addEventListener("ended", () => {
  if (audioQueue.length) {
    const next = audioQueue.shift();
    audioPlayer.src = next;
    audioPlayer.play().catch(() => {
      showToast("Unable to play audio.", "error");
    });
  }
});

function formatDate(ts) {
  if (!ts) return "";
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString();
}

async function loadLibrary() {
  try {
    const data = await api("/stories");
    state.stories = data.stories || [];
    renderLibrary();
  } catch (err) {
    showToast(err.message, "error");
  }
}

function renderLibrary() {
  libraryGrid.innerHTML = "";
  if (!state.stories.length) {
    libraryGrid.innerHTML = "<div class='library-empty'>No stories yet.</div>";
    return;
  }
  state.stories.forEach((story) => {
    const card = document.createElement("div");
    card.className = "library-card";
    const createdAt = formatDate(story.created_at);
    const tokens = story.total_tokens ? `${story.total_tokens} tokens` : "";
    card.innerHTML = `
      <div class="library-head">
        <h4>${story.title || "Untitled story"}</h4>
        <div class="library-meta">
          ${createdAt ? `<span>${createdAt}</span>` : ""}
          ${story.age_group ? `<span>${story.age_group}</span>` : ""}
          ${story.language ? `<span>${story.language}</span>` : ""}
        </div>
      </div>
      <div class="library-tags">
        ${story.style ? `<span class="badge">${story.style}</span>` : ""}
        ${story.model ? `<span class="badge">Model: ${story.model}</span>` : ""}
        ${tokens ? `<span class="badge">${tokens}</span>` : ""}
      </div>
      <div class="library-actions">
        <button class="ghost" data-action="open">Open</button>
        <button class="ghost" data-action="share">Share</button>
        <button class="ghost" data-action="pdf">PDF</button>
        <button class="ghost" data-action="zip">ZIP</button>
        <button class="ghost" data-action="delete">Delete</button>
      </div>
    `;
    card.querySelector('[data-action="open"]').addEventListener("click", async () => {
      await openStory(story.story_id, story.child_id);
    });
    card.querySelector('[data-action="share"]').addEventListener("click", async () => {
      await createShareLink(story.story_id);
    });
    card.querySelector('[data-action="pdf"]').addEventListener("click", () => {
      downloadFile(`/story/${story.story_id}/export/pdf`, "story.pdf");
    });
    card.querySelector('[data-action="zip"]').addEventListener("click", () => {
      downloadFile(`/story/${story.story_id}/export/zip`, "story.zip");
    });
    card.querySelector('[data-action="delete"]').addEventListener("click", async () => {
      if (!confirm("Delete this story?")) return;
      try {
        await api(`/story/${story.story_id}`, { method: "DELETE" });
        await loadLibrary();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
    libraryGrid.appendChild(card);
  });
}

async function openStory(storyId, childId = null) {
  try {
    const story = await api(`/story/${storyId}`);
    state.story = story;
    if (childId) {
      state.activeChildId = String(childId);
      localStorage.setItem(ACTIVE_CHILD_KEY, state.activeChildId);
      renderActiveChild();
    }
    renderStory(story);
    setView(studioView);
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function createShareLink(storyId) {
  try {
    const data = await api(`/story/${storyId}/share`, { method: "POST" });
    const shareUrl = data.share_url || "";
    if (shareUrl && navigator.clipboard) {
      await navigator.clipboard.writeText(shareUrl);
      showToast("Share link copied.");
    } else if (shareUrl) {
      showToast(`Share link: ${shareUrl}`);
    } else {
      showToast("Share link created.");
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function loadSharedStory(token) {
  try {
    state.shareToken = token;
    setAuthUI(false);
    const data = await api(`/share/${token}`);
    state.shareStory = data;
    renderStorySections(data, shareOutput);
    setView(shareView);
  } catch (err) {
    showToast(err.message, "error");
    setView(authView);
  }
}

function renderReport(report) {
  if (!report) return;
  const metrics = report.metrics || {};
  const flags = report.flags || {};
  const blockedStory = (flags.blocked_terms_in_story || []).join(", ") || "None";
  const blockedImages =
    (flags.blocked_terms_in_image_prompts || []).join(", ") || "None";
  reportBody.innerHTML = `
    <div class="report-grid">
      <div>
        <strong>Word count</strong>
        <div>${metrics.word_count ?? "—"}</div>
      </div>
      <div>
        <strong>Sentence count</strong>
        <div>${metrics.sentence_count ?? "—"}</div>
      </div>
      <div>
        <strong>Avg. sentence length</strong>
        <div>${metrics.avg_sentence_words ?? "—"}</div>
      </div>
      <div>
        <strong>Flesch-Kincaid grade</strong>
        <div>${metrics.flesch_kincaid_grade ?? "—"}</div>
      </div>
    </div>
    <div class="report-flags">
      <div><strong>Story flags:</strong> ${blockedStory}</div>
      <div><strong>Image prompt flags:</strong> ${blockedImages}</div>
    </div>
  `;
}

function renderLearning(learning) {
  if (!learning) return;
  const summary = learning.summary || "";
  const questions = learning.questions || [];
  const vocab = learning.vocabulary || [];
  const qHtml = questions
    .map(
      (q) =>
        `<li><strong>${q.question}</strong><div>${q.answer || ""}</div></li>`
    )
    .join("");
  const vHtml = vocab
    .map(
      (v) =>
        `<li><strong>${v.word}</strong>: ${v.definition}<div>${v.example || ""}</div></li>`
    )
    .join("");
  learningBody.innerHTML = `
    <div class="learning-summary">${summary || "No summary yet."}</div>
    <div class="learning-section">
      <h5>Questions</h5>
      <ul>${qHtml || "<li>—</li>"}</ul>
    </div>
    <div class="learning-section">
      <h5>Vocabulary</h5>
      <ul>${vHtml || "<li>—</li>"}</ul>
    </div>
  `;
}

async function loadReport() {
  if (!state.story) return;
  if (state.report) {
    renderReport(state.report);
    return;
  }
  try {
    const report = await api(`/story/${state.story.story_id}/report`);
    state.report = report;
    renderReport(report);
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function loadLearning() {
  if (!state.story) return;
  if (state.learning) {
    renderLearning(state.learning);
    return;
  }
  try {
    const learning = await api(`/story/${state.story.story_id}/learning`);
    state.learning = learning;
    renderLearning(learning);
  } catch (err) {
    learningBody.innerHTML =
      "<div class='muted'>No learning pack yet. Click Generate.</div>";
  }
}

async function generateNarration() {
  if (!state.story) {
    showToast("Generate a story first.", "error");
    return;
  }
  try {
    ttsBtn.disabled = true;
    storyStatus.textContent = "Generating narration...";
    const voice = voiceSelect.value || "verse";
    const updated = await api(`/story/${state.story.story_id}/tts`, {
      method: "POST",
      body: JSON.stringify({ voice, format: "mp3" }),
    });
    state.story = updated;
    renderStory(updated);
    if (state.story.sections && state.story.sections.some((s) => s.audio_url)) {
      playAllBtn.classList.remove("hidden");
    }
  } catch (err) {
    showToast(err.message, "error");
    storyStatus.textContent = state.story?.title || "Story";
  } finally {
    ttsBtn.disabled = false;
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

storyTabs.forEach((tab) => {
  tab.addEventListener("click", async () => {
    const target = tab.dataset.tab;
    setStoryTab(target);
    if (target === "report") {
      await loadReport();
    } else if (target === "learning") {
      await loadLearning();
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

shareBtn.addEventListener("click", async () => {
  if (!state.story) return;
  await createShareLink(state.story.story_id);
});

ttsBtn.addEventListener("click", async () => {
  await generateNarration();
});

playAllBtn.addEventListener("click", () => {
  if (!state.story) return;
  const urls = (state.story.sections || [])
    .map((s) => normalizeMediaUrl(s.audio_url))
    .filter(Boolean);
  if (!urls.length) {
    showToast("No narration audio yet.", "error");
    return;
  }
  playQueue(urls);
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

learningGenerateBtn.addEventListener("click", async () => {
  if (!state.story) return;
  try {
    learningGenerateBtn.disabled = true;
    const learning = await api(`/story/${state.story.story_id}/learning`, {
      method: "POST",
    });
    state.learning = learning;
    renderLearning(learning);
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    learningGenerateBtn.disabled = false;
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

libraryBtn.addEventListener("click", () => {
  loadLibrary();
  setView(libraryView);
});

studioBtn.addEventListener("click", () => {
  setView(studioView);
});

toStudioBtn.addEventListener("click", () => {
  setView(studioView);
});

newStoryBtn.addEventListener("click", () => {
  setView(studioView);
});

shareDownloadZipBtn.addEventListener("click", () => {
  if (!state.shareToken) return;
  downloadFile(`/share/${state.shareToken}/export/zip`, "story.zip");
});

shareDownloadPdfBtn.addEventListener("click", () => {
  if (!state.shareToken) return;
  downloadFile(`/share/${state.shareToken}/export/pdf`, "story.pdf");
});

openAppBtn.addEventListener("click", () => {
  window.location.href = window.location.origin;
});

storyForm.elements["chapters"].addEventListener("input", updateChaptersValue);
updateChaptersValue();

async function initApp() {
  const params = new URLSearchParams(window.location.search);
  const shareToken = params.get("share");
  if (shareToken) {
    await loadSharedStory(shareToken);
    return;
  }
  await loadSession();
}

initApp();
