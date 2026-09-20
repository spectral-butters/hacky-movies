const movies = [
  { id: "palm-springs", title: "Palm Springs", year: 2020, poster: 1, provider: "Hulu", genre: "Comedy · Sci-fi" },
  { id: "knives-out", title: "Knives Out", year: 2019, poster: 2, provider: "Prime Video", genre: "Mystery · Comedy" },
  { id: "nice-guys", title: "The Nice Guys", year: 2016, poster: 3, provider: "Netflix", genre: "Comedy · Crime" },
  { id: "game-night", title: "Game Night", year: 2018, poster: 4, provider: "Max", genre: "Comedy · Mystery" },
  { id: "about-time", title: "About Time", year: 2013, poster: 5, provider: "Netflix", genre: "Romance · Sci-fi" },
  { id: "wilderpeople", title: "Hunt for the Wilderpeople", year: 2016, poster: 6, provider: "Prime Video", genre: "Adventure · Comedy" },
  { id: "everything-everywhere", title: "Everything Everywhere", year: 2022, poster: 7, provider: "Paramount+", genre: "Action · Fantasy" },
  { id: "past-lives", title: "Past Lives", year: 2023, poster: 8, provider: "Paramount+", genre: "Drama · Romance" },
  { id: "safety-not-guaranteed", title: "Safety Not Guaranteed", year: 2012, poster: 3, provider: "Prime Video", genre: "Comedy · Sci-fi" },
  { id: "the-menu", title: "The Menu", year: 2022, poster: 2, provider: "Max", genre: "Thriller · Comedy" },
];

const movieById = Object.fromEntries(movies.map((movie) => [movie.id, movie]));

const state = {
  route: "home",
  history: [],
  drawer: false,
  modal: null,
  actionMenu: null,
  clipPlayer: null,
  toast: "",
  loading: false,
  loadingMessage: "",
  homePrompt: "A funny movie like The Matrix, but lighter",
  preferenceFilter: "all",
  onboarding: {
    step: "genres",
    status: "pending",
    genres: new Set(),
    available: [],
    maxGenres: 4,
    movies: [],
    index: 0,
    progress: { reacted: 0, rated: 0, likes: 0, dislikes: 0, enough: false, target: 15, pool: 25 },
    exhausted: false,
    reasonFor: null,
    reasonsAsked: 0,
    loading: false,
    busy: false,
    error: false,
  },
  provider: "devin",
  nights: [],
  library: {
    liked: new Set(["everything-everywhere", "knives-out", "nice-guys"]),
    disliked: new Set(["game-night"]),
    watchlist: new Set(["about-time"]),
  },
  session: {
    mode: "personal",
    backendId: null,
    eventId: null,
    movieIds: movies.slice(0, 5).map((movie) => movie.id),
    index: 0,
    reactions: {},
    originalPrompt: "",
  },
  chosenMovie: null,
  event: {
    id: null,
    inviteCode: null,
    inviteUrl: "",
    isHost: true,
    backendParticipants: [],
    name: "Friday Movie Night",
    date: "2026-09-25",
    prompt: "Something funny, under two hours",
    round: "inviting",
    myPicks: new Set(),
    nominations: new Set(),
    winner: null,
    completed: false,
    server: null,
  },
};

const app = document.querySelector("#app");
let gesture = null;
let holdTimer = null;
let toastTimer = null;
const userId = window.location.pathname.startsWith("/join/")
  ? localStorage.getItem("reelpick-guest-id") || `guest-${crypto.randomUUID()}`
  : "demo-user";
if (userId.startsWith("guest-")) localStorage.setItem("reelpick-guest-id", userId);

const DEMO_STORAGE_KEY = "reelpick-demo";
const SOUND_STORAGE_KEY = "reelpick-sound";
let demoPreference = localStorage.getItem(DEMO_STORAGE_KEY);
let demoMode = demoPreference === "1";
let soundOn = localStorage.getItem(SOUND_STORAGE_KEY) !== "0";
let demoClips = {};

function apiHeaders(extra = {}) {
  return {
    "Content-Type": "application/json",
    "X-ReelPick-User": userId,
    ...(demoPreference === null ? {} : { "X-ReelPick-Demo": demoMode ? "1" : "0" }),
    ...extra,
  };
}

async function loadDemoClips() {
  if (!demoMode || Object.keys(demoClips).length) return;
  try {
    const response = await fetch("/demo/clips/catalogue.json");
    if (!response.ok) return;
    const payload = await response.json();
    demoClips = Object.fromEntries(
      (payload.movies || [])
        .filter((entry) => entry.file && entry.title)
        .map((entry) => [
          String(entry.title).toLowerCase(),
          `/demo/clips/${encodeURIComponent(entry.file)}`,
        ]),
    );
  } catch {
    demoClips = {};
  }
}

async function setDemoMode(enabled) {
  demoMode = enabled;
  demoPreference = enabled ? "1" : "0";
  localStorage.setItem(DEMO_STORAGE_KEY, demoPreference);
  if (enabled) await loadDemoClips();
  showToast(enabled ? "Demo mode on — canned picks, no AI call" : "Demo mode off — live recommendations");
  render();
}

function catalogueMovie(movie) {
  const factual = movie.factual_metadata || {};
  return {
    id: movie.movie_id,
    title: safeText(movie.title),
    year: movie.year,
    poster: Number(factual.poster_sprite || 1),
    poster_url: movie.poster_url || null,
    provider: movie.imdb_url ? "IMDb" : "JustWatch",
    plot: safeText(factual.plot || ""),
    director: (factual.director || []).map(safeText),
    cast: (factual.cast || []).map(safeText),
    runtime_minutes: factual.runtime_minutes || null,
    rating: factual.rating || null,
    ...(movie.short_video_url || movie.clip_url
      ? { clip_url: movie.short_video_url || movie.clip_url }
      : {}),
    genre: safeText(factual.genre || "Movie"),
    watch_url:
      movie.imdb_url ||
      `https://www.justwatch.com/us/search?q=${encodeURIComponent(plainText(movie.title))}`,
  };
}

function applyBootstrap(payload) {
  const survey = payload.onboarding;
  if (survey) {
    state.onboarding.status = survey.status || "pending";
    state.onboarding.genres = new Set(survey.genres || []);
  }
  if (payload.user?.recommendation_provider) {
    state.provider = payload.user.recommendation_provider;
  }
  (payload.movies || []).forEach((movie) => {
    const normalized = catalogueMovie(movie);
    const index = movies.findIndex(({ id }) => id === normalized.id);
    if (index >= 0) movies[index] = { ...movies[index], ...normalized };
    else movies.push(normalized);
    movieById[normalized.id] = movies[index >= 0 ? index : movies.length - 1];
  });
  state.library.liked = new Set();
  state.library.disliked = new Set();
  state.library.watchlist = new Set();
  (payload.feedback || []).forEach((feedback) => {
    if (feedback.dimension === "watched_rating" && feedback.value === "liked") {
      state.library.liked.add(feedback.movie_id);
    }
    if (feedback.dimension === "watched_rating" && feedback.value === "disliked") {
      state.library.disliked.add(feedback.movie_id);
    }
    if (feedback.dimension === "watchlist" && feedback.value === "saved") {
      state.library.watchlist.add(feedback.movie_id);
    }
  });
}

async function bootstrapBackend() {
  try {
    const response = await fetch("/api/bootstrap", { headers: apiHeaders() });
    if (!response.ok) return;
    const payload = await response.json();
    if (payload.demo_mode !== undefined) demoMode = Boolean(payload.demo_mode);
    await loadDemoClips();
    applyBootstrap(payload);
    render();
    maybeOpenOnboarding(payload);
  } catch {
    // Keep the seeded catalogue when the backend is unavailable.
  }
}

function icon(name, size = 20) {
  const paths = {
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5"/>',
    home: '<path d="m3 11 9-8 9 8v9a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
    bookmark: '<path d="M6 3h12v18l-6-4-6 4z"/>',
    heart: '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8z"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    logout: '<path d="M10 17l5-5-5-5M15 12H3M21 19V5a2 2 0 0 0-2-2h-6"/>',
    user: '<path d="M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10z"/>',
    mail: '<path d="M4 4h16v16H4zM4 6l8 7 8-7"/>',
    edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v6M14 11v6"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    chevron: '<path d="m9 18 6-6-6-6"/>',
    calendar: '<path d="M3 5h18v16H3zM16 3v4M8 3v4M3 10h18"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1"/>',
    share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4"/>',
    play: '<path d="m7 4 13 8-13 8z"/>',
    pause: '<path d="M8 5v14M16 5v14"/>',
    thumbsUp: '<path d="M7 10v11H3V10zM7 18l4 3h6.5a2 2 0 0 0 2-1.6l1.2-6A2 2 0 0 0 18.7 11H15l1-4a3 3 0 0 0-3-3l-4 6H7"/>',
    thumbsDown: '<path d="M17 14V3h4v11zM17 6l-4-3H6.5a2 2 0 0 0-2 1.6l-1.2 6A2 2 0 0 0 5.3 13H9l-1 4a3 3 0 0 0 3 3l4-6h2"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    volume: '<path d="M11 5 6 9H2v6h4l5 4zM15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12"/>',
    mute: '<path d="M11 5 6 9H2v6h4l5 4zM16 9l6 6M22 9l-6 6"/>',
  };
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || ""}</svg>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function plainText(value) {
  const decoder = document.createElement("textarea");
  decoder.innerHTML = String(value);
  return decoder.value;
}

function safeText(value) {
  return escapeHtml(plainText(value));
}

function navigate(route, { replace = false } = {}) {
  if (!replace && state.route !== route) state.history.push(state.route);
  state.route = route;
  state.drawer = false;
  state.modal = null;
  state.actionMenu = null;
  state.clipPlayer = null;
  render();
}

function goBack() {
  const previous = state.history.pop() || "home";
  state.route = previous;
  state.modal = null;
  state.actionMenu = null;
  render();
}

let voiceRecorder = null;

function micButton() {
  return document.querySelector('[data-action="voice"]');
}

async function toggleVoiceCapture() {
  if (voiceRecorder) {
    voiceRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    return showToast("This browser cannot record audio");
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    return showToast("Microphone access was blocked");
  }
  const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find(
    (candidate) => MediaRecorder.isTypeSupported(candidate),
  );
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks = [];
  voiceRecorder = recorder;
  micButton()?.classList.add("mic-button--recording");
  showToast("Listening… tap the mic to stop");
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size) chunks.push(event.data);
  });
  recorder.addEventListener("stop", async () => {
    stream.getTracks().forEach((track) => track.stop());
    voiceRecorder = null;
    micButton()?.classList.remove("mic-button--recording");
    await sendVoiceClip(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
  });
  recorder.start();
}

async function sendVoiceClip(clip) {
  if (!clip.size) return showToast("Nothing was recorded");
  state.loading = true;
  state.loadingMessage = "Turning your voice into words…";
  renderOverlays();
  let transcript = "";
  try {
    const form = new FormData();
    form.append("audio", clip, "clip.webm");
    const response = await fetch("/api/transcribe", {
      method: "POST",
      headers: { "X-ReelPick-User": userId },
      body: form,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not transcribe that.");
    transcript = (payload.text || "").trim();
    if (!transcript) throw new Error("Nothing was recognised.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not transcribe that.");
  }

  const target = transcript ? applyVoiceTranscript(transcript) : "";
  if (target !== "home") {
    state.loading = false;
    state.loadingMessage = "";
    renderOverlays();
    return;
  }
  state.loadingMessage = "Finding your movies…";
  renderOverlays();
  await startPersonalRecommendations();
}

function applyVoiceTranscript(text) {
  const field = document.querySelector("#homePrompt") || document.querySelector("#eventPrompt");
  if (field) {
    field.value = text;
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
  if (field && field.id === "eventPrompt") {
    state.event.prompt = text;
    showToast("Heard you");
    return "event";
  }
  state.homePrompt = text;
  return "home";
}

function showToast(message) {
  state.toast = message;
  renderOverlays();
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    state.toast = "";
    document.querySelector(".toast")?.remove();
  }, 1800);
}

function pageHeader(title, { menu = false, right = "" } = {}) {
  return `
    <header class="topbar">
      <button class="icon-button" data-action="${menu ? "open-drawer" : "back"}" aria-label="${menu ? "Open menu" : "Go back"}">
        ${icon(menu ? "menu" : "back")}
      </button>
      ${menu ? '<div class="logo"><span class="logo-mark"></span>ReelPick</div>' : `<h1 class="topbar__title">${title}</h1>`}
      <div class="topbar__meta">${right}</div>
    </header>
  `;
}

function posterStyle(movie) {
  const url = artworkUrl(movie);
  return url
    ? ` style="background-image:url('${url}');background-size:cover;background-position:center"`
    : "";
}

function artworkUrl(movie) {
  const raw = movie?.poster_url;
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "https:") return "";
    if (!/(^|\.)media-amazon\.com$/.test(parsed.hostname)) return "";
    return parsed.href.replaceAll("'", "%27");
  } catch {
    return "";
  }
}

function clipUrl(movie) {
  const direct = movie?.clip_url;
  if (typeof direct === "string" && direct) {
    if (direct.startsWith("/demo/clips/")) return demoMode ? direct : "";
    if (isTrailerUrl(direct)) return direct;
  }
  if (!demoMode) return "";
  return demoClips[plainText(movie?.title || "").toLowerCase()] || "";
}

function isTrailerUrl(raw) {
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "https:" && parsed.hostname === "imdb-video.media-imdb.com";
  } catch {
    return false;
  }
}

function poster(movie, extraClass = "") {
  return `<div class="poster poster--${movie.poster} ${extraClass}"${posterStyle(movie)} role="img" aria-label="${movie.title} poster"></div>`;
}

function movieFacts(movie) {
  const facts = [movie.year, movie.genre];
  if (movie.runtime_minutes) facts.push(`${movie.runtime_minutes} min`);
  if (movie.rating) facts.push(`IMDb ${movie.rating.toFixed(1)}`);
  return facts.filter(Boolean).join(" · ");
}

function movieCredits(movie) {
  const rows = [];
  if (movie.director?.length) rows.push(["Director", movie.director.join(", ")]);
  if (movie.cast?.length) rows.push(["Starring", movie.cast.join(", ")]);
  return rows.length
    ? `<dl class="credits">${rows.map(([term, value]) => `<dt>${term}</dt><dd>${value}</dd>`).join("")}</dl>`
    : "";
}

function posterFrame(movie, { className = "poster-frame", badge = "" } = {}) {
  return `
    <div class="${className}"${clipTrigger(movie)}>
      ${poster(movie)}${clipBadge(movie, badge)}
    </div>
  `;
}

function clipTrigger(movie) {
  return clipUrl(movie) ? ` data-action="play-clip" data-movie="${movie.id}"` : "";
}

function clipBadge(movie, variant = "") {
  if (!clipUrl(movie)) return "";
  const size = variant === "clip-badge--large" ? 26 : 20;
  return `<span class="clip-badge ${variant}" aria-hidden="true">${icon("play", size)}</span>`;
}

function posterTile(movie, { action = "open-movie", selectable = false } = {}) {
  const resolved = action || (clipUrl(movie) ? "play-clip" : "");
  return `
    <article class="poster-tile" ${resolved && resolved !== "play-clip" ? `data-action="${resolved}" data-movie="${movie.id}"` : ""}>
      ${resolved === "play-clip" ? posterFrame(movie) : poster(movie)}
      <div class="${selectable ? "movie-tile__meta" : ""}">
        <div><h3>${movie.title}</h3><p>${movie.year}</p></div>
        ${selectable ? `<button class="overflow-button" data-action="movie-menu" data-movie="${movie.id}" aria-label="Movie actions">${icon("more", 17)}</button>` : ""}
      </div>
    </article>
  `;
}

function renderHome() {
  const watchlist = [...state.library.watchlist].map((id) => movieById[id]).filter(Boolean);
  return `
    <section class="page home-page">
      ${pageHeader("", { menu: true })}
      <div class="home-hero">
        <p class="eyebrow">AI movie matchmaker</p>
        <h1 class="display-title">What are you<br /><span class="accent">up for?</span></h1>
        <p class="lede">Say it like you'd say it to a friend. We'll turn the vibe into five sharp picks.</p>
        <div class="prompt-card">
          <textarea id="homePrompt" aria-label="What do you want to watch?" placeholder="A funny movie like The Matrix, but lighter">${escapeHtml(state.homePrompt)}</textarea>
          <div class="prompt-card__actions">
            <button class="mic-button" data-action="voice" aria-label="Use voice input">${icon("mic", 18)}</button>
            <button class="prompt-submit" data-action="start-personal">Find movies ${icon("arrow", 16)}</button>
          </div>
        </div>
        <div class="or-divider">or make it social</div>
        <button class="secondary-button" data-action="create-event">${icon("users", 18)} Host a movie night</button>
      </div>
      ${
        state.onboarding.status === "pending" || state.onboarding.status === "in_progress"
          ? `<button class="survey-banner" data-action="start-onboarding">
               <span><strong>Set up your taste</strong><small>Rate a handful of well-known movies so the picks start sharp.</small></span>
               ${icon("chevron", 17)}
             </button>`
          : ""
      }
      <div class="section-heading">
        <h2>My Watchlist</h2>
        ${watchlist.length ? '<button class="text-button" data-action="watchlist">See all</button>' : '<button class="text-button" data-action="preferences">Tune taste</button>'}
      </div>
      ${
        watchlist.length
          ? `<div class="poster-strip">${watchlist.map((movie) => posterTile(movie)).join("")}</div>`
          : `<div class="status-card" style="padding:16px"><strong style="font-size:12px">Nothing saved yet</strong><p class="lede" style="margin:5px 0 0">Drag a movie to <em>Watch later</em> in the feed and it lands here.</p></div>`
      }
    </section>
  `;
}

function renderDrawer() {
  if (!state.drawer) return "";
  const items = [
    ["home", "home", "Home", ""],
    ["bookmark", "watchlist", "My Watchlist", state.library.watchlist.size],
    ["heart", "preferences", "My Preferences", ""],
    ["users", "nights", "Movie Nights", "1"],
  ];
  return `
    <div class="drawer-shade" data-action="close-drawer">
      <aside class="drawer" data-action="noop">
        <div class="drawer__head">
          <div class="logo"><span class="logo-mark"></span>ReelPick</div>
          <button class="icon-button" data-action="close-drawer" aria-label="Close menu">${icon("close")}</button>
        </div>
        <button class="account-block" data-action="account">
          <span class="avatar">AS</span>
          <span><strong>Alex Spectral</strong><span>alexander@spectral.software</span></span>
          ${icon("chevron", 17)}
        </button>
        <nav class="drawer-nav">
          ${items
            .map(
              ([iconName, action, label, badge]) => `
                <button class="drawer-link ${state.route === action ? "drawer-link--active" : ""}" data-action="${action}">
                  ${icon(iconName, 18)} <span>${label}</span>
                  ${badge ? `<span class="drawer-link__badge">${badge}</span>` : ""}
                </button>
              `,
            )
            .join("")}
        </nav>
        <button class="drawer-link drawer-demo ${demoMode ? "drawer-demo--on" : ""}" data-action="toggle-demo" role="switch" aria-checked="${demoMode}">
          ${icon("play", 18)} <span>Demo mode</span>
          <span class="drawer-link__badge">${demoMode ? "ON" : "OFF"}</span>
        </button>
        <button class="drawer-link drawer-logout" data-action="logout">
          ${icon("logout", 18)} <span>Log out</span>
        </button>
      </aside>
    </div>
  `;
}

function renderAccount() {
  const engines = [
    ["devin", "Devin", "Agent sessions · verified IMDb lookups"],
    ["nebius", "Qwen 3.5", "Nebius Token Factory · 397B-A17B, thinking off"],
  ];
  return `
    <section class="page page--flex">
      ${pageHeader("Account")}
      <div class="profile-hero">
        <span class="avatar">AS</span>
        <h2>Alex Spectral</h2>
        <p>alexander@spectral.software</p>
      </div>
      <div class="info-card">
        <div class="info-row">${icon("user", 17)}<strong>Name</strong><span>Alex Spectral</span></div>
        <div class="info-row">${icon("mail", 17)}<strong>Email</strong><span>alexander@spectral.software</span></div>
        <button class="info-row" data-action="fake-edit">${icon("edit", 17)}<strong>Change name</strong>${icon("chevron", 15)}</button>
      </div>
      <div class="section-heading"><h2>Search engine</h2></div>
      ${demoMode ? '<p class="lede" style="margin:0 0 12px">Demo mode is on. Picks come from the bundled clips, so this choice only applies once you turn it off.</p>' : ""}
      <div class="engine-list">
        ${engines
          .map(
            ([value, label, note]) => `
              <button class="engine-option ${state.provider === value ? "engine-option--active" : ""}" data-action="set-provider" data-provider="${value}" aria-pressed="${state.provider === value}">
                <span class="engine-option__copy"><strong>${label}</strong><small>${note}</small></span>
                <span class="selection-circle">${state.provider === value ? "✓" : ""}</span>
              </button>
            `,
          )
          .join("")}
      </div>
      <div class="button-stack push-bottom">
        <button class="secondary-button" data-action="logout">${icon("logout", 17)} Log out</button>
        <button class="quiet-button" data-action="fake-delete">Delete account</button>
      </div>
    </section>
  `;
}

function preferenceEntries() {
  const seen = new Set();
  const entries = [];
  for (const [rating, ids] of [
    ["liked", state.library.liked],
    ["disliked", state.library.disliked],
  ]) {
    for (const id of ids) {
      if (seen.has(id) || !movieById[id]) continue;
      seen.add(id);
      entries.push([id, rating]);
    }
  }
  return entries.sort(([a], [b]) =>
    plainText(movieById[a].title).localeCompare(plainText(movieById[b].title)),
  );
}

function preferenceRow(id, rating) {
  const movie = movieById[id];
  if (!movie) return "";
  return `
    <article class="watch-card">
      ${posterFrame(movie, { className: "watch-card__art" })}
      <div class="watch-card__copy">
        <h3>${movie.title}</h3>
        <p>${movie.year} · ${movie.genre}</p>
        <div class="inline-actions">
          <div class="pref-switch" role="group" aria-label="Rating for ${movie.title}">
            <button class="pref-switch__side ${rating === "liked" ? "pref-switch__side--on" : ""}" data-action="move-liked" data-movie="${movie.id}" aria-pressed="${rating === "liked"}">${icon("thumbsUp", 14)} Liked</button>
            <button class="pref-switch__side ${rating === "disliked" ? "pref-switch__side--on" : ""}" data-action="move-disliked" data-movie="${movie.id}" aria-pressed="${rating === "disliked"}">${icon("thumbsDown", 14)} Disliked</button>
          </div>
          <button class="overflow-button" data-action="movie-menu" data-movie="${movie.id}" aria-label="Movie actions">${icon("more", 16)}</button>
        </div>
      </div>
    </article>
  `;
}

const LIKE_REASONS = [
  ["story", "Story"],
  ["humour", "Humour"],
  ["characters", "Characters"],
  ["cast", "Actors"],
  ["atmosphere", "Atmosphere"],
  ["action", "Action"],
  ["visuals", "Visual style"],
  ["emotion", "Emotional impact"],
];

const DISLIKE_REASONS = [
  ["pacing", "Too slow"],
  ["violence_or_horror", "Too violent"],
  ["violence_or_horror", "Too scary"],
  ["confusing", "Too confusing"],
  ["humour", "Didn’t like the humour"],
  ["cast", "Didn’t like the actors"],
  ["emotion", "Too emotional"],
  ["story", "Not interested in the story"],
  ["other", "Other"],
];

const REASON_PROMPT_LIMIT = 3;

function maybeOpenOnboarding(payload) {
  if (state.onboarding.status !== "pending") return;
  if (state.route !== "home" || state.event.inviteCode) return;
  if ((payload.feedback || []).length) return;
  startOnboarding();
}

async function loadOnboarding({ reset = false } = {}) {
  const survey = state.onboarding;
  survey.loading = true;
  survey.error = false;
  if (reset) survey.reasonsAsked = 0;
  render();
  try {
    const response = await fetch("/api/onboarding", { headers: apiHeaders() });
    if (!response.ok) throw new Error("Could not load the taste survey.");
    const payload = await response.json();
    survey.status = payload.status;
    survey.available = payload.available_genres || [];
    survey.maxGenres = payload.max_genres || 4;
    survey.genres = new Set(payload.genres || []);
    survey.movies = addRecommendedMovies(payload.movies || []);
    survey.index = 0;
    survey.progress = payload.progress || survey.progress;
    survey.exhausted = Boolean(payload.exhausted);
    return payload;
  } catch (error) {
    survey.error = true;
    survey.movies = [];
    survey.index = 0;
    showToast(error instanceof Error ? error.message : "Could not load the taste survey.");
    return null;
  } finally {
    survey.loading = false;
    render();
  }
}

async function startOnboarding() {
  const survey = state.onboarding;
  survey.step = "genres";
  navigate("onboarding");
  await loadOnboarding({ reset: true });
}

async function saveOnboardingGenres() {
  const survey = state.onboarding;
  try {
    const response = await fetch("/api/onboarding/genres", {
      method: "PUT",
      headers: apiHeaders(),
      body: JSON.stringify({ genres: [...survey.genres] }),
    });
    if (!response.ok) throw new Error("Could not save your genres.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not save your genres.");
  }
  survey.step = "round";
  await loadOnboarding();
}

async function finishOnboarding(status) {
  state.onboarding.status = status;
  try {
    await fetch("/api/onboarding/finish", {
      method: "POST",
      headers: apiHeaders(),
      body: JSON.stringify({ status }),
    });
  } catch {
    // The survey is advisory; a failed write should not block the app.
  }
  navigate("home");
  await bootstrapBackend();
  showToast(status === "skipped" ? "You can take the survey any time from My Preferences" : "Taste profile saved");
}

function onboardingMovie() {
  const survey = state.onboarding;
  return movieById[survey.movies[survey.index]];
}

async function recordOnboardingReaction(action) {
  const survey = state.onboarding;
  const movie = onboardingMovie();
  if (!movie || survey.busy || survey.loading) return;
  survey.busy = true;
  let feedback = null;
  if (action === "liked" || action === "disliked") {
    feedback = await submitWatched(movie.id, action, "onboarding");
  } else if (action === "unwatched") {
    await submitFeedback(movie.id, "viewing_status", "unwatched", {
      sourceSurface: "onboarding",
    });
  } else if (action === "watchlist") {
    await submitFeedback(movie.id, "viewing_status", "unwatched", {
      sourceSurface: "onboarding",
    });
    await setWatchlist(movie.id, true, "onboarding");
  }
  survey.progress.reacted += 1;
  if (action === "liked") survey.progress.likes += 1;
  if (action === "disliked") survey.progress.dislikes += 1;
  if (action === "liked" || action === "disliked") survey.progress.rated += 1;
  survey.progress.enough =
    survey.progress.rated >= 8 && survey.progress.likes >= 2 && survey.progress.dislikes >= 1;

  const wantsReason =
    feedback &&
    survey.reasonsAsked < REASON_PROMPT_LIMIT &&
    (action === "disliked" || survey.progress.reacted % 4 === 0);
  survey.busy = false;
  if (wantsReason) {
    survey.reasonsAsked += 1;
    survey.reasonFor = { movieId: movie.id, action, feedbackId: feedback.feedback_id };
    render();
    return;
  }
  advanceOnboarding();
}

async function saveOnboardingReason(code, label) {
  const survey = state.onboarding;
  const pending = survey.reasonFor;
  survey.reasonFor = null;
  render();
  if (!pending || !code) return advanceOnboarding();
  await submitFeedback(pending.movieId, "watched_rating", pending.action, {
    sourceSurface: "onboarding",
    reasonCode: code,
    reasonText: label,
    supersededFeedbackId: pending.feedbackId,
  });
  advanceOnboarding();
}

function advanceOnboarding() {
  const survey = state.onboarding;
  survey.busy = false;
  if (survey.index + 1 < survey.movies.length) {
    survey.index += 1;
    render();
    return;
  }
  if (survey.progress.reacted >= survey.progress.pool) return finishOnboarding("complete");
  survey.step = survey.progress.enough || survey.progress.reacted >= survey.progress.target ? "checkpoint" : "round";
  if (survey.step === "checkpoint") {
    render();
    return;
  }
  loadOnboarding().then((payload) => {
    if (payload && !payload.movies.length) finishOnboarding("complete");
  });
}

function renderOnboarding() {
  const survey = state.onboarding;
  if (survey.step === "genres") return renderOnboardingGenres();
  if (survey.step === "checkpoint") return renderOnboardingCheckpoint();
  return renderOnboardingRound();
}

function renderOnboardingGenres() {
  const survey = state.onboarding;
  const chosen = survey.genres.size;
  return `
    <section class="page page--flex">
      ${pageHeader("Set up your taste")}
      <p class="eyebrow" style="margin-top:28px">Step 1 of 2</p>
      <h1 class="display-title display-title--small">What do you<br /><span class="accent">usually watch?</span></h1>
      <p class="lede">Select up to ${survey.maxGenres}. This is a starting hint, not a filter — you can change it later.</p>
      <div class="genre-grid">
        ${survey.available
          .map(
            ({ key, label }) => `
              <button class="genre-chip ${survey.genres.has(key) ? "genre-chip--active" : ""}" data-action="toggle-genre" data-genre="${key}" aria-pressed="${survey.genres.has(key)}">${label}</button>
            `,
          )
          .join("")}
      </div>
      <div class="button-stack push-bottom">
        <button class="primary-button" data-action="onboarding-genres-done">${chosen ? `Continue with ${chosen}` : "Skip genres"} ${icon("arrow", 17)}</button>
        <button class="quiet-button" data-action="onboarding-skip">Skip the survey</button>
      </div>
    </section>
  `;
}

function renderOnboardingRound() {
  const survey = state.onboarding;
  const movie = survey.loading ? null : onboardingMovie();
  if (survey.error) {
    return `
      <section class="page page--flex">
        ${pageHeader("Set up your taste")}
        <div class="empty-state"><div><h2>Could not load the next round</h2><p>Check your connection and try again — nothing you have rated is lost.</p><button class="primary-button" data-action="onboarding-retry">Try again</button><button class="quiet-button" data-action="onboarding-skip">Skip the survey</button></div></div>
      </section>
    `;
  }
  if (survey.loading) {
    return `
      <section class="page page--flex">
        ${pageHeader("Set up your taste")}
        <div class="empty-state"><div><span class="loading-spinner"></span><h2>Loading movies</h2></div></div>
      </section>
    `;
  }
  if (!movie) {
    return `
      <section class="page page--flex">
        ${pageHeader("Set up your taste")}
        <div class="empty-state"><div><h2>Nothing left to rate</h2><p>${survey.exhausted ? "You have been through the whole calibration set." : "No more movies to show right now."}</p><button class="primary-button" data-action="onboarding-done">Start exploring</button></div></div>
      </section>
    `;
  }
  const rated = survey.progress.rated;
  return `
    <section class="page page--flex">
      ${pageHeader("Set up your taste")}
      <div class="survey-progress">
        <span>${survey.index + 1} of ${survey.movies.length} in this round</span>
        <span>${rated} rated${survey.progress.enough ? " · enough signal" : ""}</span>
      </div>
      <article class="survey-card">
        ${posterFrame(movie, { className: "survey-card__art", badge: "clip-badge--large" })}
        <h2>${movie.title}</h2>
        <p>${movie.year} · ${movie.genre}</p>
      </article>
      <div class="survey-actions">
        <button class="survey-action survey-action--like" data-action="survey-react" data-reaction="liked">${icon("thumbsUp", 18)} Liked</button>
        <button class="survey-action survey-action--dislike" data-action="survey-react" data-reaction="disliked">${icon("thumbsDown", 18)} Disliked</button>
        <button class="survey-action" data-action="survey-react" data-reaction="unwatched">${icon("eye", 18)} Haven’t watched</button>
        <button class="survey-action" data-action="survey-react" data-reaction="watchlist">${icon("bookmark", 18)} Add to watchlist</button>
      </div>
      <div class="button-stack push-bottom">
        ${survey.progress.enough ? '<button class="secondary-button" data-action="onboarding-done">I’m done — start exploring</button>' : ""}
        <button class="quiet-button" data-action="onboarding-skip">Skip the survey</button>
      </div>
    </section>
  `;
}

function renderOnboardingCheckpoint() {
  const survey = state.onboarding;
  return `
    <section class="page page--flex">
      ${pageHeader("Set up your taste")}
      <p class="eyebrow" style="margin-top:34px">Taste profile</p>
      <h1 class="display-title display-title--small">We already<br /><span class="accent">get your taste.</span></h1>
      <div class="count-hero">
        <strong>${survey.progress.rated}</strong>
        <p>movies rated<br />${survey.progress.likes} liked · ${survey.progress.dislikes} disliked</p>
      </div>
      <p class="lede">Continue for sharper recommendations, or start exploring now.</p>
      <div class="button-stack push-bottom">
        <button class="primary-button" data-action="onboarding-continue">Rate five more ${icon("arrow", 17)}</button>
        <button class="secondary-button" data-action="onboarding-done">Start exploring</button>
      </div>
    </section>
  `;
}

function renderReasonSheet() {
  const pending = state.onboarding.reasonFor;
  if (!pending) return "";
  const movie = movieById[pending.movieId];
  const reasons = pending.action === "liked" ? LIKE_REASONS : DISLIKE_REASONS;
  return `
    <div class="modal-shade" data-action="skip-reason">
      <div class="modal" data-action="noop">
        <div class="modal__handle"></div>
        <h2 style="font-size:18px;margin:0 0 4px">${pending.action === "liked" ? "What worked for you?" : "What didn’t work for you?"}</h2>
        <p class="lede" style="margin:0 0 14px">${movie ? movie.title : ""} · optional, one tap</p>
        <div class="reason-grid">
          ${reasons
            .map(
              ([code, label], position) => `
                <button class="reason-chip" data-action="pick-reason" data-code="${code}" data-label="${escapeHtml(label)}" data-position="${position}">${label}</button>
              `,
            )
            .join("")}
        </div>
        <button class="quiet-button" data-action="skip-reason">Skip</button>
      </div>
    </div>
  `;
}

function renderPreferences() {
  const entries = preferenceEntries();
  const likedCount = entries.filter(([, rating]) => rating === "liked").length;
  const filter = state.preferenceFilter;
  const visible = entries.filter(([, rating]) => filter === "all" || rating === filter);
  const filters = [
    ["all", `All ${entries.length}`],
    ["liked", `Liked ${likedCount}`],
    ["disliked", `Disliked ${entries.length - likedCount}`],
  ];
  return `
    <section class="page">
      ${pageHeader("My Preferences")}
      <button class="survey-banner" data-action="start-onboarding">
        <span><strong>${state.onboarding.status === "complete" ? "Retake the taste survey" : "Take the taste survey"}</strong><small>Rate well-known movies to calibrate your recommendations.</small></span>
        ${icon("chevron", 17)}
      </button>
      ${
        entries.length
          ? `<div class="filter-bar" role="group" aria-label="Filter preferences">
               ${filters
                 .map(
                   ([value, label]) => `
                     <button class="filter-chip ${filter === value ? "filter-chip--active" : ""}" data-action="pref-filter" data-filter="${value}" aria-pressed="${filter === value}">${label}</button>
                   `,
                 )
                 .join("")}
             </div>
             <p class="lede" style="margin:0 0 14px">Tap the other side of a switch to move a movie straight away.</p>
             ${
               visible.length
                 ? `<div class="watch-list">${visible.map(([id, rating]) => preferenceRow(id, rating)).join("")}</div>`
                 : `<div class="status-card" style="padding:17px;color:var(--muted);font-size:11px">Nothing ${filter === "liked" ? "liked" : "disliked"} yet.</div>`
             }`
          : `<div class="empty-state"><div><div class="empty-state__icon">${icon("heart", 28)}</div><h2>Nothing here yet</h2><p>Movies you rate will appear here, liked and disliked together.</p><button class="primary-button" data-action="home">Find movies</button></div></div>`
      }
    </section>
  `;
}

function renderWatchlist() {
  const list = [...state.library.watchlist].map((id) => movieById[id]);
  return `
    <section class="page">
      ${pageHeader("My Watchlist")}
      ${
        list.length
          ? `<div class="watch-list">
              ${list
                .map(
                  (movie) => `
                    <article class="watch-card">
                      ${poster(movie)}
                      <div class="watch-card__copy">
                        <h3>${movie.title}</h3>
                        <p>${movie.year} · ${movie.genre}</p>
                        <div class="inline-actions">
                          <button class="small-button small-button--accent" data-action="where-to-watch" data-movie="${movie.id}">Watch</button>
                          <button class="small-button" data-action="watched-from-list" data-movie="${movie.id}">Already watched</button>
                          <button class="overflow-button" data-action="watch-menu" data-movie="${movie.id}">${icon("more", 16)}</button>
                        </div>
                      </div>
                    </article>
                  `,
                )
                .join("")}
            </div>`
          : `<div class="empty-state"><div><div class="empty-state__icon">${icon("bookmark", 28)}</div><h2>Your list is empty</h2><p>Movies you save for later will appear here.</p><button class="primary-button" data-action="home">Find movies</button></div></div>`
      }
    </section>
  `;
}

function startFeed(mode, movieIds, backendId = null) {
  state.session = {
    mode,
    backendId: backendId || state.session.backendId,
    eventId: mode === "personal" ? null : state.event.id,
    movieIds,
    index: 0,
    reactions: mode === "personal" ? state.session.reactions : {},
    originalPrompt: mode === "personal" ? state.homePrompt : state.event.prompt,
  };
  navigate("feed");
}

function movieTitles(ids) {
  return [...ids]
    .map((id) => movieById[id]?.title)
    .filter(Boolean)
    .map(plainText);
}

function addRecommendedMovies(recommendations) {
  return recommendations.map((recommendation) => {
    const movie = {
      ...recommendation,
      title: safeText(recommendation.title),
      genre: safeText(recommendation.genre),
      provider: safeText(recommendation.provider),
      hook: safeText(recommendation.hook || ""),
      plot: safeText(recommendation.plot || ""),
      director: (recommendation.director || []).map(safeText),
      cast: (recommendation.cast || []).map(safeText),
      runtime_minutes: recommendation.runtime_minutes || null,
      rating: recommendation.rating || null,
    };
    const existingIndex = movies.findIndex(({ id }) => id === movie.id);
    if (existingIndex >= 0) movies[existingIndex] = movie;
    else movies.push(movie);
    movieById[movie.id] = movie;
    return movie.id;
  });
}

async function requestRecommendations({ prompt, count, mode, excludedIds = [] }) {
  state.loading = true;
  state.loadingMessage = mode === "round1" ? "Building picks for your group…" : "Finding your movies…";
  renderOverlays();
  try {
    const response = await fetch("/api/recommendations", {
      method: "POST",
      headers: apiHeaders(),
      body: JSON.stringify({
        prompt,
        count,
        session_id: excludedIds.length ? state.session.backendId : null,
        event_id: state.event.id,
        mode: mode === "personal" ? "personal" : "event_nomination",
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Movie search failed.");
    return {
      movieIds: addRecommendedMovies(payload.movies),
      sessionId: payload.session_id,
      shortfallReason: payload.shortfall_reason,
    };
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Movie search failed.");
    return null;
  } finally {
    state.loading = false;
    state.loadingMessage = "";
    renderOverlays();
  }
}

async function startPersonalRecommendations({ additional = false } = {}) {
  const count = additional ? Math.max(1, 5 - personalLikes().length) : 5;
  if (!additional) state.session.reactions = {};
  const excludedIds = additional ? state.session.movieIds : [];
  const result = await requestRecommendations({
    prompt: state.homePrompt,
    count,
    mode: "personal",
    excludedIds,
  });
  if (result?.movieIds.length) {
    startFeed("personal", result.movieIds, result.sessionId);
  } else if (result) {
    showToast(result.shortfallReason || "No additional verified movies found.");
  }
}

function roundOneSessionIsResumable() {
  return (
    state.session.mode === "round1" &&
    state.session.eventId === state.event.id &&
    state.session.movieIds.length > 0
  );
}

async function startRoundOneRecommendations() {
  const result = await requestRecommendations({
    prompt: state.event.prompt,
    count: 5,
    mode: "round1",
    excludedIds: [],
  });
  if (!result?.movieIds.length) {
    if (result) showToast(result.shortfallReason || "No verified movies found.");
    return;
  }
  state.event.round = "round1";
  state.event.myPicks = new Set();
  startFeed("round1", result.movieIds, result.sessionId);
}

function currentMovie() {
  return movieById[state.session.movieIds[state.session.index]];
}

function sessionCount(type) {
  return Object.values(state.session.reactions).filter((value) => value === type).length;
}

function renderFeed() {
  const movie = currentMovie();
  const total = state.session.movieIds.length;
  const mode = state.session.mode;
  const isRoundTwo = mode === "round2";
  const likedLabel =
    mode === "personal"
      ? `${sessionCount("like")} liked`
      : mode === "round1"
        ? `${sessionCount("like")}/2 selected`
        : "Vote on every movie";
  const priorReaction = state.session.reactions[movie.id];
  return `
    <section class="feed-page" id="feedSurface">
      ${feedClip(movie)}
      <header class="topbar topbar--feed">
        <button class="icon-button icon-button--ghost" data-action="exit-feed" aria-label="Exit feed">${icon("back")}</button>
        <h1 class="topbar__title">${state.session.index + 1}/${total}</h1>
        <div class="topbar__meta">
          ${clipUrl(movie) ? soundButton() : ""}
          <span>${likedLabel}</span>
        </div>
      </header>
      <div class="feed-guide"><span class="feed-guide__dot"></span>${isRoundTwo ? "Round 2" : "Hold to react"}</div>
      <div class="feed-copy">
        <h1>${movie.title}</h1>
        <p>${movie.year}</p>
        <div class="feed-hint"><span>↕</span> Swipe to browse · Hold and drag to choose</div>
      </div>
      ${clipProgress(movie)}
      ${priorReaction ? `<div class="reaction-stamp reaction-stamp--show">${reactionLabel(priorReaction)}</div>` : '<div class="reaction-stamp" id="reactionStamp"></div>'}
      <div class="decision-overlay" id="decisionOverlay">
        ${decisionZone("dislike", "Dislike", "thumbsDown", "--red")}
        ${decisionZone("like", mode === "round1" ? "Pick it" : "Like", "thumbsUp", "--green")}
        ${decisionZone("watched", "Already watched", "eye", "--blue")}
        ${decisionZone("later", isRoundTwo ? "Unavailable" : "Watch later", "bookmark", "--amber", isRoundTwo)}
        <div class="drag-origin"></div>
        <div class="drag-indicator" id="dragIndicator"></div>
      </div>
    </section>
  `;
}

function feedClip(movie) {
  const clip = clipUrl(movie);
  if (clip) {
    return `
      <video class="feed-clip feed-clip--video" id="feedClip" src="${clip}" autoplay ${soundOn ? "" : "muted"} loop playsinline preload="auto"></video>
      <div class="feed-scrim"></div>
    `;
  }
  return `<div class="feed-clip poster--${movie.poster}"${posterStyle(movie)} id="feedClip"></div>`;
}

function clipProgress(movie) {
  if (!clipUrl(movie)) return '<div class="clip-progress"></div>';
  return `
    <div class="clip-progress clip-progress--real">
      <i class="clip-progress__bar" id="clipBar"></i>
    </div>
  `;
}

function bindClipProgress(videoSelector = "#feedClip", barSelector = "#clipBar") {
  const video = document.querySelector(videoSelector);
  const bar = document.querySelector(barSelector);
  if (!video || !bar || typeof video.play !== "function") return;
  const paint = () => {
    const total = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 0;
    bar.style.width = total ? `${Math.min(100, (video.currentTime / total) * 100)}%` : "0%";
  };
  video.addEventListener("timeupdate", paint);
  video.addEventListener("loadedmetadata", paint);
  video.addEventListener("seeked", paint);
  paint();
}

function soundButton() {
  return `
    <button class="icon-button icon-button--ghost sound-toggle" id="soundToggle" data-action="toggle-sound" aria-pressed="${soundOn}" aria-label="${soundOn ? "Mute clip" : "Unmute clip"}">
      ${icon(soundOn ? "volume" : "mute", 17)}
    </button>
  `;
}

function paintSoundButton() {
  const button = document.querySelector("#soundToggle");
  if (!button) return;
  button.innerHTML = icon(soundOn ? "volume" : "mute", 17);
  button.setAttribute("aria-pressed", String(soundOn));
  button.setAttribute("aria-label", soundOn ? "Mute clip" : "Unmute clip");
}

function startClip(video, onBlocked) {
  if (!video || typeof video.play !== "function") return;
  video.muted = !soundOn;
  video.volume = 1;
  video.play().catch(() => {
    if (!soundOn) return;
    soundOn = false;
    video.muted = true;
    video.play().catch(() => {});
    onBlocked?.();
  });
}

function applyClipSound() {
  startClip(document.querySelector("#feedClip"), () => {
    paintSoundButton();
    showToast("Your browser blocked sound — tap the speaker to turn it on");
  });
  paintSoundButton();
}

function renderClipPlayer() {
  if (!state.clipPlayer) return "";
  const movie = movieById[state.clipPlayer.movieId];
  const clip = movie && clipUrl(movie);
  if (!clip) return "";
  return `
    <div class="clip-player" data-action="close-clip">
      <video class="clip-player__video" id="clipPlayerVideo" src="${clip}" autoplay loop playsinline preload="auto"></video>
      <div class="feed-scrim"></div>
      <button class="icon-button icon-button--ghost clip-player__close" data-action="close-clip" aria-label="Close clip">${icon("close")}</button>
      <div class="clip-player__copy">
        <h2>${movie.title}</h2>
        <p>${movie.year} · ${movie.genre}</p>
      </div>
      <div class="clip-progress clip-progress--real clip-player__progress">
        <i class="clip-progress__bar" id="clipPlayerBar"></i>
      </div>
    </div>
  `;
}

function bindClipPlayer() {
  const video = document.querySelector("#clipPlayerVideo");
  if (!video) return;
  const feed = document.querySelector("#feedClip");
  if (feed && typeof feed.pause === "function") feed.pause();
  startClip(video);
  bindClipProgress("#clipPlayerVideo", "#clipPlayerBar");
}

function decisionZone(action, label, iconName, color, disabled = false) {
  return `
    <div class="decision-zone ${disabled ? "decision-zone--disabled" : ""}" data-zone="${action}" style="--zone-color:var(${color})">
      <div class="decision-zone__content">
        <span class="decision-zone__icon">${icon(iconName, 23)}</span>
        <strong>${label}</strong>
        ${disabled ? "<span>Watch later is off during voting</span>" : ""}
      </div>
    </div>
  `;
}

function reactionLabel(reaction) {
  return { like: "LIKED", dislike: "DISLIKED", later: "SAVED", watched: "WATCHED", neutral: "NOTED" }[reaction] || "";
}

function renderPersonalResults() {
  const liked = Object.entries(state.session.reactions)
    .filter(([, value]) => value === "like")
    .map(([id]) => movieById[id])
    .filter(Boolean);
  const need = Math.max(0, 5 - liked.length);
  return `
    <section class="page page--flex">
      ${pageHeader("Your picks")}
      <p class="eyebrow" style="margin-top:34px">Your session</p>
      <h1 class="display-title display-title--small">Here’s what<br /><span class="accent">landed.</span></h1>
      <div class="count-hero">
        <strong>${liked.length}</strong>
        <p>movie${liked.length === 1 ? "" : "s"} liked<br />from this search</p>
      </div>
      ${
        liked.length
          ? `<div class="liked-scroll">${liked.map((movie) => posterTile(movie, { action: "" })).join("")}</div>`
          : `<div class="status-card" style="padding:18px"><strong>No likes yet.</strong><p class="lede">That’s useful too — the next set will steer away from everything you passed on.</p></div>`
      }
      <div class="button-stack push-bottom">
        <button class="primary-button" data-action="choose-likes" ${liked.length ? "" : "disabled"}>Choose from my likes ${icon("arrow", 17)}</button>
        ${need ? `<button class="secondary-button" data-action="more-recommendations">Show ${need} more</button>` : ""}
        <button class="quiet-button" data-action="home">Start over</button>
      </div>
    </section>
  `;
}

function personalLikes() {
  return Object.entries(state.session.reactions)
    .filter(([, value]) => value === "like")
    .map(([id]) => movieById[id])
    .filter(Boolean);
}

function renderPersonalChoice() {
  return `
    <section class="page page--flex">
      ${pageHeader("Choose a movie")}
      <p class="eyebrow" style="margin-top:32px">Final call</p>
      <h1 class="display-title display-title--small">One of these<br /><span class="accent">is the one.</span></h1>
      <div style="margin-top:22px">
        ${personalLikes()
          .map(
            (movie) => `
              <article class="selection-card">
                ${posterFrame(movie, { className: "selection-card__art" })}
                <div class="selection-card__copy">
                  <h3>${movie.title}</h3>
                  <p>${movieFacts(movie)}</p>
                  ${movie.plot ? `<p class="selection-card__plot">${movie.plot}</p>` : ""}
                  ${movieCredits(movie)}
                  <button class="small-button small-button--accent" data-action="choose-personal-movie" data-movie="${movie.id}">Choose this movie</button>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderPersonalFinal() {
  const movie = movieById[state.chosenMovie];
  return `
    <section class="page page--flex">
      ${pageHeader("Your movie")}
      <div class="final-poster"${clipTrigger(movie)}>${poster(movie)}${clipBadge(movie, "clip-badge--large")}</div>
      <div class="final-copy">
        <p class="eyebrow">Tonight’s pick</p>
        <h1>${movie.title}</h1>
        <p>${movie.year} · ${movie.genre}</p>
      </div>
      <div class="button-stack push-bottom">
        <button class="primary-button" data-action="where-to-watch" data-movie="${movie.id}">Watch ${icon("arrow", 17)}</button>
        ${state.library.watchlist.has(movie.id) ? "" : '<button class="secondary-button" data-action="save-chosen">Save to Watchlist</button>'}
        <button class="quiet-button" data-action="home">Start over</button>
      </div>
    </section>
  `;
}

function renderNights() {
  const hosting = state.nights.filter((night) => night.role === "host");
  const joined = state.nights.filter((night) => night.role !== "host");
  const card = (night) => `
    <button class="event-card" data-action="open-event" data-code="${night.invite_code}">
      <div class="event-card__top">
        <div><h3>${safeText(night.name)}</h3><p>${formatDate(night.event_date || "")} · ${night.role === "host" ? "Hosted by you" : "Joined by link"}</p></div>
        <span class="status-pill status-pill--orange">${eventStatusLabel(night.status)}</span>
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between">
        <div class="avatars">
          <span class="avatars__count">${night.participant_count} ${night.participant_count === 1 ? "person" : "people"}</span>
        </div>
        ${icon("chevron", 18)}
      </div>
    </button>
  `;
  return `
    <section class="page page--flex">
      ${pageHeader("Movie Nights")}
      <button class="primary-button" style="margin-top:22px" data-action="create-event">${icon("users", 18)} Host a movie night</button>
      <div class="section-heading"><h2>Hosting</h2></div>
      ${
        hosting.length
          ? `<div class="event-list">${hosting.map(card).join("")}</div>`
          : `<div class="status-card" style="padding:17px;color:var(--muted);font-size:11px">You are not hosting a movie night yet.</div>`
      }
      <div class="section-heading"><h2>Joined</h2></div>
      ${
        joined.length
          ? `<div class="event-list">${joined.map(card).join("")}</div>`
          : `<div class="status-card" style="padding:17px;color:var(--muted);font-size:11px">Movie nights you join will appear here.</div>`
      }
    </section>
  `;
}

function eventStatusLabel(status) {
  return (
    {
      inviting: "Inviting",
      round1: "Round 1 · Choosing",
      round2: "Round 2 · Voting",
      final: "Host deciding",
      completed: "Completed",
    }[status] || "Inviting"
  );
}

async function loadNights() {
  try {
    const response = await fetch("/api/events", { headers: apiHeaders() });
    if (!response.ok) return;
    const payload = await response.json();
    state.nights = payload.items || [];
    if (state.route === "nights") render();
  } catch {
    /* the list stays as it was */
  }
}

async function openEvent(inviteCode) {
  state.event.inviteCode = inviteCode;
  try {
    const response = await fetch(`/api/events/${encodeURIComponent(inviteCode)}/state`, {
      headers: apiHeaders(),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Movie night not found.");
    navigate("lobby");
    applyEventState(payload);
    startEventPolling();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Movie night not found.");
  }
}

function formatDate(date) {
  if (!date) return "Date not set";
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${date}T12:00:00`));
}

function renderCreateEvent() {
  return `
    <section class="page page--flex">
      ${pageHeader("Host a movie night")}
      <p class="eyebrow" style="margin-top:32px">New event</p>
      <h1 class="display-title display-title--small">Bring the crew.<br /><span class="accent">Skip the debate.</span></h1>
      <div class="field-group">
        <label class="field-label" for="eventName">Event name *</label>
        <input class="text-field" id="eventName" value="${escapeHtml(state.event.name)}" placeholder="Friday Movie Night" />
      </div>
      <div class="field-group">
        <label class="field-label" for="eventDate">Date <span style="color:var(--muted);font-weight:400">Optional</span></label>
        <input class="text-field" id="eventDate" type="date" value="${state.event.date}" />
      </div>
      <div class="field-group">
        <label class="field-label" for="eventPrompt">What are you in the mood for? *</label>
        <textarea class="text-area" id="eventPrompt" placeholder="Something funny, under two hours">${escapeHtml(state.event.prompt)}</textarea>
      </div>
      <div class="chip-row" style="margin-top:10px">
        <button class="chip" data-action="event-prompt-chip" data-value="Something funny, under two hours">Funny + short</button>
        <button class="chip" data-action="event-prompt-chip" data-value="A clever crowd-pleaser nobody has seen">Nobody’s seen it</button>
      </div>
      <div class="push-bottom">
        <button class="primary-button" data-action="submit-event">Create movie night ${icon("arrow", 17)}</button>
      </div>
    </section>
  `;
}

function participants(stage = "lobby") {
  const colors = ["var(--orange)", "var(--blue)", "var(--green)", "var(--amber)"];
  return (state.event.backendParticipants || []).map((participant, index) => {
    const name = safeText(participant.display_name);
    const initials = safeText(
      plainText(participant.display_name)
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
        .toUpperCase(),
    );
    const waiting = stage === "round2" ? "Voting" : stage === "round1" ? "Choosing" : "Joined";
    const finished = stage === "round2" ? "Finished" : "Ready";
    const status =
      stage === "lobby"
        ? participant.role === "host"
          ? "Host"
          : "Joined"
        : participant.ready
          ? finished
          : waiting;
    return [
      initials || "RP",
      name + (participant.is_you ? " (you)" : ""),
      status,
      colors[index % colors.length],
      participant.role,
    ];
  });
}

function participantList(stage) {
  return participants(stage)
    .map(
      ([initials, name, status, color, role]) => `
        <div class="participant">
          <span class="avatar" style="background:${color};${color === "var(--amber)" ? "color:var(--ink)" : ""}">${initials}</span>
          <span><strong>${name}${role === "host" ? " · Host" : ""}</strong><small>${role === "host" ? "Created this movie night" : "Joined by link"}</small></span>
          <span class="participant__status">${status}</span>
        </div>
      `,
    )
    .join("");
}

function renderLobby() {
  const server = eventServer();
  const inviteUrl = safeText(state.event.inviteUrl || "Invite link is being created…");
  const participantCount = server.participant_count ?? state.event.backendParticipants.length;
  const roundOpen = server.status === "round1";
  const controls = roundOpen
    ? `
        <button class="primary-button" data-action="get-my-picks">Round 1 is open · get my movies ${icon("arrow", 17)}</button>
        ${state.event.isHost ? `<button class="secondary-button" data-action="manage-round1">Host controls</button>` : ""}
      `
    : state.event.isHost
      ? `
        <button class="primary-button" data-action="start-round1">Start choosing ${icon("arrow", 17)}</button>
        <button class="secondary-button" data-action="manage-event">Manage event</button>
      `
      : `<p class="lede">Waiting for the host to start Round 1. This screen moves on by itself.</p>`;
  return `
    <section class="page page--flex">
      ${pageHeader(state.event.name, { right: "Round 1" })}
      <p class="eyebrow" style="margin-top:26px">Event lobby</p>
      <h1 class="display-title display-title--small">The room<br /><span class="accent">is open.</span></h1>
      <p class="lede">${state.event.prompt}</p>
      <div class="invite-card">
        <span class="invite-card__label">Invite your people</span>
        <div class="invite-card__link">
          <code>${inviteUrl}</code>
          <button class="small-button" data-action="copy-link">${icon("copy", 14)}</button>
          <button class="small-button" data-action="share-link">${icon("share", 14)}</button>
        </div>
      </div>
      <div class="name-field">
        <label class="field-label" for="displayName">Your name in this room</label>
        <div class="name-field__row">
          <input class="text-field" id="displayName" value="${safeText(guestName())}" maxlength="40" />
          <button class="small-button" data-action="save-name">Save</button>
        </div>
      </div>
      <div class="section-heading"><h2>${participantCount} ${participantCount === 1 ? "participant" : "participants"}</h2><span style="font-size:9px;color:var(--muted)">${state.event.isHost ? "You’re the host" : "You joined by link"}</span></div>
      <div class="participant-list">${participantList("lobby")}</div>
      <div class="button-stack push-bottom">
        ${controls}
      </div>
    </section>
  `;
}

function renderRound1Select() {
  const selected = state.event.myPicks;
  return `
    <section class="page page--flex">
      ${pageHeader("Your nominations", { right: `${selected.size}/2` })}
      <p class="eyebrow" style="margin-top:28px">Round 1</p>
      <h1 class="display-title display-title--small">Pick up to<br /><span class="accent">two movies.</span></h1>
      <p class="lede">Replace a pick anytime before you lock them in.</p>
      <div class="nomination-list">
        ${state.session.movieIds
          .map((id) => {
            const movie = movieById[id];
            const isSelected = selected.has(id);
            return `
              <button class="nomination ${isSelected ? "nomination--selected" : ""}" data-action="toggle-nomination" data-movie="${id}">
                ${poster(movie)}
                <span><strong>${movie.title}</strong><span>${movie.year} · ${movie.genre}</span></span>
                <span class="selection-circle">${isSelected ? "✓" : ""}</span>
              </button>
            `;
          })
          .join("")}
      </div>
      <div class="push-bottom">
        <button class="primary-button" data-action="lock-picks" ${selected.size ? "" : "disabled"}>Lock in my pick${selected.size === 1 ? "" : "s"} ${icon("arrow", 17)}</button>
      </div>
    </section>
  `;
}

function waitingVisual(centerStrong, centerSmall) {
  return `
    <div class="waiting-visual">
      <div class="waiting-visual__center"><strong>${centerStrong}</strong><span>${centerSmall}</span></div>
      <span class="waiting-avatar">AS</span><span class="waiting-avatar">MI</span><span class="waiting-avatar">NO</span><span class="waiting-avatar">JO</span><span class="waiting-avatar">•••</span>
    </div>
  `;
}

function renderWaitRound1() {
  const server = eventServer();
  const total = server.participant_count || 1;
  const ready = server.ready_count || 0;
  return `
    <section class="page page--flex">
      ${pageHeader(state.event.name, { right: "Round 1" })}
      ${waitingVisual(`${ready}/${total}`, "people ready")}
      <div class="waiting-copy">
        <h1>Your picks are in.</h1>
        <p>${ready >= total ? "Everyone has nominated." : "Still waiting on the room."} Nominations stay hidden until the host closes the round.</p>
      </div>
      <div class="button-stack push-bottom">
        ${state.event.isHost ? `<button class="primary-button" data-action="manage-round1">Open host controls</button>` : ""}
        <button class="secondary-button" data-action="edit-picks">Edit my picks</button>
      </div>
    </section>
  `;
}

function renderManageRound1() {
  const server = eventServer();
  const inviteUrl = safeText(state.event.inviteUrl || "Invite link unavailable");
  return `
    <section class="page page--flex">
      ${pageHeader("Manage Round 1")}
      <p class="eyebrow" style="margin-top:26px">${state.event.name}</p>
      <h1 class="display-title display-title--small">Nominations<br /><span class="accent">are coming in.</span></h1>
      <div class="round-summary">
        <div class="round-stat"><strong>${server.ready_count || 0}/${server.participant_count || 1}</strong><span>ready</span></div>
        <div class="round-stat"><strong>${server.nomination_count || 0}</strong><span>nominations</span></div>
        <div class="round-stat"><strong>${server.participant_count || 1}</strong><span>people</span></div>
      </div>
      <div class="section-heading"><h2>Participants</h2></div>
      <div class="participant-list">${participantList("round1")}</div>
      <div class="invite-card">
        <span class="invite-card__label">Invite link</span>
        <div class="invite-card__link"><code>${inviteUrl}</code><button class="small-button" data-action="copy-link">${icon("copy", 14)}</button><span></span></div>
      </div>
      <div class="push-bottom">
        <button class="primary-button" data-action="close-round1" ${server.nomination_count ? "" : "disabled"}>Close Round 1</button>
      </div>
    </section>
  `;
}

function renderWaitRound2() {
  const server = eventServer();
  const total = server.participant_count || 1;
  const ready = server.ready_count || 0;
  const hostChoosing = server.status === "final";
  return `
    <section class="page page--flex">
      ${pageHeader(state.event.name, { right: "Round 2" })}
      ${waitingVisual(hostChoosing ? "…" : `${ready}/${total}`, hostChoosing ? "host deciding" : "votes finished")}
      <div class="waiting-copy">
        <h1>${hostChoosing ? "Voting is closed." : "Your votes are in."}</h1>
        <p>${hostChoosing ? "The host is picking tonight’s movie." : "Results stay hidden until the host closes voting."}</p>
      </div>
      <div class="push-bottom">
        ${state.event.isHost ? `<button class="primary-button" data-action="manage-round2">Open host controls</button>` : ""}
      </div>
    </section>
  `;
}

function renderManageRound2() {
  const server = eventServer();
  return `
    <section class="page page--flex">
      ${pageHeader("Manage Round 2")}
      <p class="eyebrow" style="margin-top:26px">${state.event.name}</p>
      <h1 class="display-title display-title--small">Voting is<br /><span class="accent">under way.</span></h1>
      <div class="round-summary">
        <div class="round-stat"><strong>${(server.nominated_movie_ids || []).length}</strong><span>movies</span></div>
        <div class="round-stat"><strong>${server.participant_count || 1}</strong><span>voters</span></div>
        <div class="round-stat"><strong>${server.ready_count || 0}/${server.participant_count || 1}</strong><span>finished</span></div>
      </div>
      <div class="section-heading"><h2>Voting status</h2></div>
      <div class="participant-list">${participantList("round2")}</div>
      <div class="push-bottom">
        <button class="primary-button" data-action="close-round2">Close Round 2</button>
      </div>
    </section>
  `;
}

function finalists() {
  return (eventServer().finalists || [])
    .filter((entry) => movieById[entry.movie_id])
    .map((entry) => ({ ...entry, movie: movieById[entry.movie_id] }));
}

function renderFinalists() {
  const ranked = finalists();
  return `
    <section class="page page--flex">
      ${pageHeader("Final choice")}
      <p class="eyebrow" style="margin-top:28px">Host decision</p>
      <h1 class="display-title display-title--small">Choose tonight’s<br /><span class="accent">movie.</span></h1>
      <p class="lede">The room voted on ${ranked.length} nomination${ranked.length === 1 ? "" : "s"}. The last call is yours.</p>
      <div class="finalist-grid">
        ${ranked
          .map(
            (entry) => `
              <article class="finalist-card">
                ${poster(entry.movie)}
                <div class="finalist-card__copy">
                  <h3>${entry.movie.title}</h3>
                  <p>${entry.movie.year}<br />${entry.likes} like${entry.likes === 1 ? "" : "s"} · ${entry.dislikes} dislike${entry.dislikes === 1 ? "" : "s"}</p>
                  <button class="small-button small-button--accent" data-action="select-winner" data-movie="${entry.movie.id}">Choose this movie</button>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="status-card" style="margin-top:14px;padding:14px;font-size:10px;color:var(--muted)">
        Ranked by likes, then fewest dislikes.
      </div>
    </section>
  `;
}

function renderMissingWinner(title) {
  return `
    <section class="page page--flex">
      ${pageHeader(title)}
      <div class="empty-state"><div><h2>Loading the winner</h2><p>The chosen movie is not in this device’s catalogue yet.</p><button class="primary-button" data-action="refresh-catalogue">Reload it</button></div></div>
    </section>
  `;
}

function renderWinner() {
  const server = eventServer();
  const movie = movieById[state.event.winner];
  if (!movie) return renderMissingWinner("Tonight’s movie");
  const host = (server.participants || []).find((participant) => participant.role === "host");
  return `
    <section class="page page--flex" style="position:relative">
      ${pageHeader("Tonight’s movie")}
      <div class="winner-confetti"><span></span><span></span><span></span><span></span><span></span></div>
      <div class="final-poster" style="position:relative"${clipTrigger(movie)}>${poster(movie)}${clipBadge(movie, "clip-badge--large")}</div>
      <div class="final-copy" style="position:relative">
        <p class="eyebrow">The room has spoken</p>
        <h1>${movie.title}</h1>
        <p>${movie.year} · Chosen by ${safeText(host?.display_name || "the host")}</p>
      </div>
      <div class="status-card" style="margin-top:20px;padding:14px;text-align:center">
        <strong style="font-size:11px">${state.event.name}</strong>
        <p style="margin:4px 0 0;color:var(--muted);font-size:9px">${formatDate(state.event.date)} · ${server.participant_count || 1} participants</p>
      </div>
      <div class="button-stack push-bottom">
        <button class="primary-button" data-action="where-to-watch" data-movie="${movie.id}">Watch ${icon("arrow", 17)}</button>
        <button class="secondary-button" data-action="end-night">End movie night</button>
      </div>
    </section>
  `;
}

function renderCompleted() {
  const server = eventServer();
  const movie = movieById[state.event.winner];
  if (!movie) return renderMissingWinner("Movie night");
  const host = (server.participants || []).find((participant) => participant.role === "host");
  return `
    <section class="page page--flex">
      ${pageHeader("Completed movie night")}
      <p class="eyebrow" style="margin-top:28px">Completed</p>
      <h1 class="display-title display-title--small">${state.event.name}</h1>
      <p class="lede">${formatDate(state.event.date)} · Hosted by ${safeText(host?.display_name || "the host")} · ${server.participant_count || 1} participants</p>
      <div class="selection-card" style="margin-top:24px">
        ${poster(movie)}
        <div class="selection-card__copy">
          <p class="eyebrow" style="margin:0 0 8px">Winning movie</p>
          <h3>${movie.title}</h3>
          <p>${movie.year} · ${movie.genre}</p>
          <button class="small-button small-button--accent" data-action="where-to-watch" data-movie="${movie.id}">Watch</button>
        </div>
      </div>
      <div class="section-heading"><h2>Nominations</h2></div>
      <div class="poster-strip" style="margin:0">${finalists().map((entry) => posterTile(entry.movie, { action: "" })).join("")}</div>
      <div class="push-bottom"><button class="secondary-button" data-action="nights">Back to Movie Nights</button></div>
    </section>
  `;
}

function pendingCopy(action) {
  const server = eventServer();
  const waiting = (server.participant_count || 1) - (server.ready_count || 0);
  if (waiting <= 0) return `Everyone has ${action}. Close the round?`;
  return `${waiting} ${waiting === 1 ? "person has" : "people have"} not ${action} yet. Close the round anyway?`;
}

function renderModal() {
  if (!state.modal) return "";
  if (state.modal.type === "watched") {
    const movie = movieById[state.modal.movieId];
    return `
      <div class="modal-shade" data-action="close-modal">
        <div class="modal" data-action="noop">
          <div class="modal__handle"></div>
          <h2>Did you like it?</h2>
          <p>You’ve already watched <strong>${movie.title}</strong>. Your answer helps tune future picks.</p>
          <div class="choice-buttons">
            <button class="choice-button choice-button--yes" data-action="watched-answer" data-answer="yes">Yes</button>
            <button class="choice-button choice-button--no" data-action="watched-answer" data-answer="no">No</button>
            <button class="choice-button" data-action="watched-answer" data-answer="unsure">Not sure</button>
          </div>
        </div>
      </div>
    `;
  }
  if (state.modal.type === "movie") {
    const movie = movieById[state.modal.movieId];
    return `
      <div class="modal-shade" data-action="close-modal">
        <div class="modal" data-action="noop">
          <div class="modal__handle"></div>
          <div style="display:grid;grid-template-columns:72px 1fr;gap:13px;align-items:center;margin-bottom:18px">
            ${poster(movie)}
            <div><p class="eyebrow" style="margin:0 0 5px">Recommended for you</p><h2 style="font-size:20px">${movie.title}</h2><p style="margin:4px 0 0">${movieFacts(movie)}</p></div>
          </div>
          ${movie.plot ? `<p class="lede" style="margin:0 0 12px">${movie.plot}</p>` : ""}
          ${movieCredits(movie)}
          <div class="button-stack">
            ${clipUrl(movie) ? `<button class="secondary-button" data-action="play-clip" data-movie="${movie.id}">${icon("play", 17)} Play the short</button>` : ""}
            <button class="primary-button" data-action="where-to-watch" data-movie="${movie.id}">Watch</button>
            <button class="secondary-button" data-action="quick-save" data-movie="${movie.id}">${state.library.watchlist.has(movie.id) ? "Remove from Watchlist" : "Save to Watchlist"}</button>
          </div>
        </div>
      </div>
    `;
  }
  const confirmation = {
    close1: {
      title: "Close Round 1?",
      copy: pendingCopy("locked in their movies"),
      confirm: "confirm-close1",
      button: "Close Round 1",
    },
    close2: {
      title: "Close Round 2?",
      copy: pendingCopy("finished voting"),
      confirm: "confirm-close2",
      button: "Close Round 2",
    },
    winner: {
      title: `Choose “${movieById[state.modal.movieId]?.title || "this movie"}”?`,
      copy: "This will reveal tonight’s movie to everyone in the event.",
      confirm: "confirm-winner",
      button: "Confirm choice",
    },
    logout: {
      title: "Log out?",
      copy: "This is a mocked hackathon account. You can sign straight back in.",
      confirm: "confirm-logout",
      button: "Log out",
    },
  }[state.modal.type];
  if (!confirmation) return "";
  return `
    <div class="modal-shade" data-action="close-modal">
      <div class="modal" data-action="noop">
        <div class="modal__handle"></div>
        <h2>${confirmation.title}</h2>
        <p>${confirmation.copy}</p>
        <div class="button-stack">
          <button class="primary-button" data-action="${confirmation.confirm}" ${state.modal.movieId ? `data-movie="${state.modal.movieId}"` : ""}>${confirmation.button}</button>
          <button class="secondary-button" data-action="close-modal">Keep waiting</button>
        </div>
      </div>
    </div>
  `;
}

function renderActionMenu() {
  if (!state.actionMenu) return "";
  const movie = movieById[state.actionMenu.movieId];
  const type = state.actionMenu.type;
  let actions = [];
  if (type === "preference") {
    actions = state.library.disliked.has(movie.id)
      ? [
          ["remove-preference", "Remove from preferences"],
          ["move-liked", "Move to liked"],
        ]
      : [
          ["remove-preference", "Remove from preferences"],
          ["move-disliked", "Move to disliked"],
          ["add-watchlist", "Add to Watchlist"],
        ];
  } else {
    actions = [
      ["remove-watchlist", "Remove from Watchlist"],
      ["move-liked", "Move to liked"],
      ["move-disliked", "Move to disliked"],
    ];
  }
  return `
    <div class="action-menu" data-action="close-action-menu">
      <div class="action-menu__card" data-action="noop">
        <div class="action-menu__title">${movie.title}</div>
        ${actions.map(([action, label]) => `<button data-action="${action}" data-movie="${movie.id}">${label}</button>`).join("")}
        <button data-action="close-action-menu">Cancel</button>
      </div>
    </div>
  `;
}

function renderOverlays() {
  document.querySelector(".drawer-shade")?.remove();
  document.querySelectorAll(".modal-shade").forEach((node) => node.remove());
  document.querySelector(".action-menu")?.remove();
  document.querySelector(".clip-player")?.remove();
  document.querySelector(".loading-shade")?.remove();
  document.querySelector(".toast")?.remove();
  const loading = state.loading
    ? `<div class="loading-shade" role="status"><div class="loading-card"><span class="loading-spinner"></span><strong>${state.loadingMessage}</strong><p>This can take a minute.</p></div></div>`
    : "";
  app.insertAdjacentHTML(
    "beforeend",
    renderDrawer() +
      renderModal() +
      renderReasonSheet() +
      renderActionMenu() +
      renderClipPlayer() +
      loading +
      (state.toast ? `<div class="toast">${state.toast}</div>` : ""),
  );
  bindClipPlayer();
}

function render() {
  const routes = {
    home: renderHome,
    onboarding: renderOnboarding,
    account: renderAccount,
    preferences: renderPreferences,
    watchlist: renderWatchlist,
    nights: renderNights,
    "create-event": renderCreateEvent,
    lobby: renderLobby,
    feed: renderFeed,
    "personal-results": renderPersonalResults,
    "personal-choice": renderPersonalChoice,
    "personal-final": renderPersonalFinal,
    "round1-select": renderRound1Select,
    "wait-round1": renderWaitRound1,
    "manage-round1": renderManageRound1,
    "wait-round2": renderWaitRound2,
    "manage-round2": renderManageRound2,
    finalists: renderFinalists,
    winner: renderWinner,
    completed: renderCompleted,
  };
  app.innerHTML = (routes[state.route] || renderHome)();
  renderOverlays();
  bindPosterStrips();
  if (state.route === "feed") bindFeedGestures();
}

async function submitFeedback(movieId, dimension, value, options = {}) {
  const context = options.context || "personal";
  const body = {
    movie_id: movieId,
    dimension,
    value,
    source_surface: options.sourceSurface || state.route,
    context,
    session_id:
      options.sessionId || (context === "session" ? state.session.backendId : null),
    event_id: context === "event" ? state.event.id : null,
    reason_code: options.reasonCode || null,
    reason_text: options.reasonText || null,
    superseded_feedback_id: options.supersededFeedbackId || null,
  };
  try {
    const response = await fetch("/api/feedback", {
      method: "POST",
      headers: apiHeaders({ "Idempotency-Key": crypto.randomUUID() }),
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not save feedback.");
    return payload.feedback;
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not save feedback.");
    return null;
  }
}

async function setWatchlist(movieId, saved, sourceSurface = state.route) {
  if (saved) state.library.watchlist.add(movieId);
  else state.library.watchlist.delete(movieId);
  persistLibrary();
  render();
  await submitFeedback(movieId, "watchlist", saved ? "saved" : "not_saved", {
    sourceSurface,
  });
}

async function submitWatched(movieId, rating, sourceSurface) {
  state.library.watchlist.delete(movieId);
  if (rating === "liked") {
    state.library.liked.add(movieId);
    state.library.disliked.delete(movieId);
  } else if (rating === "disliked") {
    state.library.disliked.add(movieId);
    state.library.liked.delete(movieId);
  }
  persistLibrary();
  const sessionId = sourceSurface === "personal_feed" ? state.session.backendId : null;
  await submitFeedback(movieId, "viewing_status", "watched", {
    sourceSurface,
    sessionId,
  });
  return submitFeedback(movieId, "watched_rating", rating, {
    sourceSurface,
    sessionId,
  });
}

function recordReaction(movieId, reaction) {
  state.session.reactions[movieId] = reaction;
  if (state.session.mode === "personal" && reaction === "like") {
    submitFeedback(movieId, "recommendation_interest", "interested", {
      context: "session",
      sourceSurface: "personal_feed",
    });
  }
  if (state.session.mode === "personal" && reaction === "dislike") {
    submitFeedback(movieId, "recommendation_interest", "not_interested", {
      context: "session",
      sourceSurface: "personal_feed",
    });
  }
  if (state.session.mode === "personal" && reaction === "later") {
    state.library.watchlist.add(movieId);
    submitFeedback(movieId, "watchlist", "saved", {
      sourceSurface: "personal_feed",
    });
  }
  if (state.session.mode === "round2" && ["like", "dislike"].includes(reaction)) {
    submitFeedback(movieId, "group_vote", reaction, {
      context: "event",
      sourceSurface: "event_vote",
    });
  }
  persistLibrary();
}

function handleReaction(reaction) {
  const movie = currentMovie();
  if (reaction === "watched") {
    state.modal = { type: "watched", movieId: movie.id, source: "feed" };
    renderOverlays();
    return;
  }
  if (state.session.mode === "round2" && reaction === "later") {
    cancelDecisionOverlay();
    showToast("Watch later is unavailable during voting");
    return;
  }
  if (state.session.mode === "round1" && reaction === "like") {
    const picked = Object.entries(state.session.reactions).filter(([, value]) => value === "like" && value).length;
    if (picked >= 2 && state.session.reactions[movie.id] !== "like") {
      cancelDecisionOverlay();
      showToast("You already have two picks");
      return;
    }
  }
  recordReaction(movie.id, reaction);
  showReactionStamp(reaction);
  window.setTimeout(nextMovie, 350);
}

function showReactionStamp(reaction) {
  const stamp = document.querySelector("#reactionStamp");
  if (!stamp) return;
  stamp.textContent = reactionLabel(reaction);
  stamp.classList.remove("reaction-stamp--show");
  void stamp.offsetWidth;
  stamp.classList.add("reaction-stamp--show");
  if (navigator.vibrate) navigator.vibrate(28);
}

function nextMovie() {
  if (state.session.index < state.session.movieIds.length - 1) {
    state.session.index += 1;
    render();
  } else {
    finishFeed();
  }
}

async function submitEventVotes() {
  const votes = {};
  Object.entries(state.session.reactions).forEach(([movieId, reaction]) => {
    if (reaction === "like") votes[movieId] = "like";
    else if (reaction === "dislike") votes[movieId] = "dislike";
    else votes[movieId] = "abstain";
  });
  try {
    applyEventState(await postEvent("/votes", { votes, finished: true }), {
      navigateOnChange: false,
    });
    startEventPolling();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not send your votes.");
  }
}

function previousMovie() {
  if (state.session.index > 0) {
    state.session.index -= 1;
    render();
  } else {
    showToast("You’re at the first movie");
  }
}

function finishFeed() {
  if (state.session.mode === "personal") navigate("personal-results", { replace: true });
  if (state.session.mode === "round1") {
    state.event.myPicks = new Set(
      Object.entries(state.session.reactions)
        .filter(([, value]) => value === "like")
        .map(([id]) => id)
        .slice(0, 2),
    );
    navigate("round1-select", { replace: true });
  }
  if (state.session.mode === "round2") {
    submitEventVotes();
    navigate("wait-round2", { replace: true });
  }
}

function bindPosterStrips() {
  document.querySelectorAll(".poster-strip").forEach((strip) => {
    strip.addEventListener(
      "wheel",
      (event) => {
        if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
        if (strip.scrollWidth <= strip.clientWidth) return;
        event.preventDefault();
        strip.scrollLeft += event.deltaY;
      },
      { passive: false },
    );
  });
}

function bindFeedGestures() {
  const surface = document.querySelector("#feedSurface");
  if (!surface) return;
  surface.addEventListener("pointerdown", onPointerDown);
  surface.addEventListener("pointermove", onPointerMove);
  surface.addEventListener("pointerup", onPointerUp);
  surface.addEventListener("pointercancel", onPointerCancel);
  surface.addEventListener("contextmenu", (event) => event.preventDefault());
  applyClipSound();
  bindClipProgress();
}

function onPointerDown(event) {
  if (event.target.closest("button")) return;
  gesture = {
    startX: event.clientX,
    startY: event.clientY,
    x: event.clientX,
    y: event.clientY,
    active: false,
    selected: null,
    pointerId: event.pointerId,
  };
  event.currentTarget.setPointerCapture?.(event.pointerId);
  holdTimer = window.setTimeout(() => activateDecisionOverlay(), 150);
}

function activateDecisionOverlay() {
  if (!gesture) return;
  gesture.active = true;
  document.querySelector("#decisionOverlay")?.classList.add("decision-overlay--active");
  if (navigator.vibrate) navigator.vibrate(12);
}

function onPointerMove(event) {
  if (!gesture || event.pointerId !== gesture.pointerId) return;
  gesture.x = event.clientX;
  gesture.y = event.clientY;
  const dx = gesture.x - gesture.startX;
  const dy = gesture.y - gesture.startY;
  if (!gesture.active && Math.hypot(dx, dy) > 14) window.clearTimeout(holdTimer);
  if (!gesture.active) return;
  event.preventDefault();
  updateDecisionSelection(dx, dy);
}

function updateDecisionSelection(dx, dy) {
  const indicator = document.querySelector("#dragIndicator");
  const max = 120;
  const distance = Math.hypot(dx, dy);
  const scale = distance > max ? max / distance : 1;
  const limitedX = dx * scale;
  const limitedY = dy * scale;
  if (indicator) indicator.style.transform = `translate(calc(-50% + ${limitedX}px), calc(-50% + ${limitedY}px))`;

  let selected = null;
  if (distance >= 52) {
    if (dx < 0 && dy < 0) selected = "dislike";
    if (dx >= 0 && dy < 0) selected = "like";
    if (dx < 0 && dy >= 0) selected = "watched";
    if (dx >= 0 && dy >= 0) selected = "later";
  }
  if (state.session.mode === "round2" && selected === "later") selected = null;
  gesture.selected = selected;
  document.querySelectorAll("[data-zone]").forEach((zone) => {
    const active = zone.dataset.zone === selected;
    zone.classList.toggle("decision-zone--selected", active);
    zone.classList.toggle("decision-zone--weak", Boolean(selected) && !active);
  });
}

function onPointerUp(event) {
  if (!gesture || event.pointerId !== gesture.pointerId) return;
  window.clearTimeout(holdTimer);
  const finished = { ...gesture };
  gesture = null;
  if (finished.active) {
    if (finished.selected) handleReaction(finished.selected);
    else cancelDecisionOverlay();
    return;
  }
  const dy = event.clientY - finished.startY;
  if (dy < -52) nextMovie();
  else if (dy > 52) previousMovie();
  else toggleFeedClip();
}

function toggleFeedClip() {
  const clip = document.querySelector("#feedClip");
  if (!clip) return;
  const paused = clip.classList.toggle("paused");
  if (typeof clip.play !== "function") return;
  if (paused) clip.pause();
  else clip.play().catch(() => {});
}

function onPointerCancel() {
  window.clearTimeout(holdTimer);
  gesture = null;
  cancelDecisionOverlay();
}

function cancelDecisionOverlay() {
  document.querySelector("#decisionOverlay")?.classList.remove("decision-overlay--active");
  document.querySelectorAll("[data-zone]").forEach((zone) => zone.classList.remove("decision-zone--selected", "decision-zone--weak"));
  const indicator = document.querySelector("#dragIndicator");
  if (indicator) indicator.style.transform = "translate(-50%, -50%)";
}


function persistLibrary() {
  try {
    localStorage.setItem(
      "reelpick-library",
      JSON.stringify({
        liked: [...state.library.liked],
        disliked: [...state.library.disliked],
        watchlist: [...state.library.watchlist],
        catalog: movies,
      }),
    );
  } catch {
    // The prototype works without storage access.
  }
}

function restoreLibrary() {
  try {
    const stored = JSON.parse(localStorage.getItem("reelpick-library"));
    if (!stored) return;
    state.library.liked = new Set(stored.liked || []);
    state.library.disliked = new Set(stored.disliked || []);
    state.library.watchlist = new Set(stored.watchlist || []);
    if (Array.isArray(stored.catalog)) addRecommendedMovies(stored.catalog);
  } catch {
    // Keep the seeded mock data.
  }
}

app.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  const movieId = target.dataset.movie;
  if (action === "noop") {
    event.stopPropagation();
    return;
  }
  const simpleRoutes = ["home", "account", "preferences", "watchlist", "nights"];
  if (simpleRoutes.includes(action)) {
    if (action === "nights") loadNights();
    return navigate(action);
  }
  const handlers = {
    "open-drawer": () => {
      state.drawer = true;
      renderOverlays();
    },
    "close-drawer": () => {
      state.drawer = false;
      renderOverlays();
    },
    back: goBack,
    "create-event": () => navigate("create-event"),
    "start-personal": () => {
      state.homePrompt = document.querySelector("#homePrompt")?.value.trim() || state.homePrompt;
      startPersonalRecommendations();
    },
    voice: () => toggleVoiceCapture(),
    "open-movie": () => {
      state.modal = { type: "movie", movieId };
      renderOverlays();
    },
    "play-clip": () => {
      state.modal = null;
      state.actionMenu = null;
      state.clipPlayer = { movieId };
      renderOverlays();
    },
    "close-clip": () => {
      state.clipPlayer = null;
      renderOverlays();
      applyClipSound();
    },
    "close-modal": () => {
      state.modal = null;
      renderOverlays();
    },
    "quick-save": async () => {
      const saved = !state.library.watchlist.has(movieId);
      await setWatchlist(movieId, saved, "movie_detail");
      state.modal = null;
      render();
      showToast(saved ? "Saved to Watchlist" : "Removed from Watchlist");
    },
    "where-to-watch": () => {
      const movie = movieById[movieId];
      const destination =
        movie.watch_url || `https://www.justwatch.com/us/search?q=${encodeURIComponent(plainText(movie.title))}`;
      window.open(destination, "_blank", "noopener,noreferrer");
    },
    "pref-filter": () => {
      state.preferenceFilter = target.dataset.filter;
      render();
    },
    "movie-menu": () => {
      state.actionMenu = { type: "preference", movieId };
      renderOverlays();
    },
    "watch-menu": () => {
      state.actionMenu = { type: "watchlist", movieId };
      renderOverlays();
    },
    "close-action-menu": () => {
      state.actionMenu = null;
      renderOverlays();
    },
    "remove-preference": async () => {
      state.library.liked.delete(movieId);
      state.library.disliked.delete(movieId);
      state.actionMenu = null;
      persistLibrary();
      render();
      await submitFeedback(movieId, "watched_rating", "neutral", {
        sourceSurface: "preferences",
      });
    },
    "move-liked": async () => {
      state.actionMenu = null;
      await submitWatched(movieId, "liked", "preferences");
      render();
      showToast("Moved to liked");
    },
    "move-disliked": async () => {
      state.actionMenu = null;
      await submitWatched(movieId, "disliked", "preferences");
      render();
      showToast("Moved to disliked");
    },
    "add-watchlist": async () => {
      state.actionMenu = null;
      await setWatchlist(movieId, true, "preferences");
      showToast("Added to Watchlist");
    },
    "remove-watchlist": async () => {
      state.actionMenu = null;
      await setWatchlist(movieId, false, "watchlist");
    },
    "watched-from-list": () => {
      state.modal = { type: "watched", movieId, source: "watchlist" };
      renderOverlays();
    },
    "watched-answer": async () => {
      const { movieId: watchedId, source } = state.modal;
      const answer = target.dataset.answer;
      const rating = answer === "yes" ? "liked" : answer === "no" ? "disliked" : "neutral";
      await submitWatched(watchedId, rating, source === "feed" ? "personal_feed" : "watchlist");
      if (source === "feed") {
        const reaction = "watched";
        state.session.reactions[watchedId] = reaction;
        state.modal = null;
        renderOverlays();
        showReactionStamp(reaction);
        window.setTimeout(nextMovie, 300);
      } else {
        state.modal = null;
        render();
        showToast("Watchlist updated");
      }
    },
    "exit-feed": () => goBack(),
    "choose-likes": () => navigate("personal-choice"),
    "more-recommendations": () => {
      startPersonalRecommendations({ additional: true });
    },
    "choose-personal-movie": () => {
      state.chosenMovie = movieId;
      navigate("personal-final");
    },
    "save-chosen": async () => {
      await setWatchlist(state.chosenMovie, true, "final_choice");
      showToast("Saved to Watchlist");
    },
    "event-prompt-chip": () => {
      const input = document.querySelector("#eventPrompt");
      if (input) input.value = target.dataset.value;
    },
    "submit-event": async () => {
      const name = document.querySelector("#eventName")?.value.trim();
      const date = document.querySelector("#eventDate")?.value;
      const prompt = document.querySelector("#eventPrompt")?.value.trim();
      if (!name || !prompt) return showToast("Add an event name and group prompt");
      state.event.name = name;
      state.event.date = date;
      state.event.prompt = prompt;
      state.event.round = "inviting";
      state.event.completed = false;
      state.loading = true;
      state.loadingMessage = "Creating your movie night…";
      renderOverlays();
      try {
        const response = await fetch("/api/events", {
          method: "POST",
          headers: apiHeaders(),
          body: JSON.stringify({
            name,
            event_date: date || null,
            prompt,
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || "Could not create movie night.");
        state.event.id = payload.event_id;
        state.event.inviteCode = payload.invite_code;
        state.event.inviteUrl = payload.invite_url;
        state.event.isHost = true;
        state.event.backendParticipants = payload.participants || [];
        await refreshEventState();
        startEventPolling();
      } catch (error) {
        showToast(error instanceof Error ? error.message : "Could not create movie night.");
        return;
      } finally {
        state.loading = false;
        state.loadingMessage = "";
      }
      navigate("lobby", { replace: true });
    },
    "copy-link": async () => {
      try {
        await navigator.clipboard.writeText(state.event.inviteUrl);
      } catch {
        // Clipboard may be restricted in preview iframes.
      }
      showToast("Invite link copied");
    },
    "share-link": async () => {
      if (navigator.share) {
        await navigator.share({ title: state.event.name, url: state.event.inviteUrl });
      } else {
        try {
          await navigator.clipboard.writeText(state.event.inviteUrl);
        } catch {
          // Clipboard may be restricted in preview iframes.
        }
      }
      showToast("Invite ready to share");
    },
    "manage-event": () => navigate("manage-round1"),
    "start-round1": async () => {
      try {
        applyEventState(await postEvent("/round", { status: "round1" }), {
          navigateOnChange: false,
        });
      } catch (error) {
        return showToast(error instanceof Error ? error.message : "Could not start Round 1.");
      }
      startEventPolling();
      startRoundOneRecommendations();
    },
    "get-my-picks": () => {
      if (!roundOneSessionIsResumable()) return startRoundOneRecommendations();
      const done = state.session.movieIds.every((id) => state.session.reactions[id]);
      return navigate(done ? "round1-select" : "feed");
    },
    "save-name": async () => {
      const name = document.querySelector("#displayName")?.value.trim();
      if (!name) return showToast("Add a name first");
      localStorage.setItem("reelpick-display-name", name);
      try {
        await postEvent("/join", { display_name: name });
        await refreshEventState();
        showToast("Name updated");
      } catch (error) {
        showToast(error instanceof Error ? error.message : "Could not update your name.");
      }
    },
    "toggle-nomination": () => {
      if (state.event.myPicks.has(movieId)) state.event.myPicks.delete(movieId);
      else if (state.event.myPicks.size < 2) state.event.myPicks.add(movieId);
      else return showToast("You can nominate up to two movies");
      render();
    },
    "lock-picks": async () => {
      try {
        applyEventState(await postEvent("/nominations", { movie_ids: [...state.event.myPicks] }), {
          navigateOnChange: false,
        });
      } catch (error) {
        return showToast(error instanceof Error ? error.message : "Could not lock your picks.");
      }
      startEventPolling();
      navigate("wait-round1", { replace: true });
    },
    "edit-picks": () => navigate("round1-select"),
    "manage-round1": () => navigate("manage-round1"),
    "close-round1": () => {
      state.modal = { type: "close1" };
      renderOverlays();
    },
    "confirm-close1": async () => {
      state.modal = null;
      try {
        applyEventState(await postEvent("/round", { status: "round2" }), {
          navigateOnChange: false,
        });
      } catch (error) {
        return showToast(error instanceof Error ? error.message : "Could not close Round 1.");
      }
      await startVotingRound();
    },
    "manage-round2": () => navigate("manage-round2"),
    "close-round2": () => {
      state.modal = { type: "close2" };
      renderOverlays();
    },
    "confirm-close2": async () => {
      state.modal = null;
      try {
        applyEventState(await postEvent("/round", { status: "final" }), {
          navigateOnChange: false,
        });
      } catch (error) {
        return showToast(error instanceof Error ? error.message : "Could not close Round 2.");
      }
      navigate("finalists", { replace: true });
    },
    "select-winner": () => {
      state.modal = { type: "winner", movieId };
      renderOverlays();
    },
    "confirm-winner": async () => {
      state.modal = null;
      try {
        applyEventState(await postEvent("/winner", { movie_id: movieId }), {
          navigateOnChange: false,
        });
      } catch (error) {
        return showToast(error instanceof Error ? error.message : "Could not save the winner.");
      }
      navigate("winner", { replace: true });
    },
    "end-night": () => {
      state.event.completed = true;
      state.event.round = "completed";
      navigate("completed", { replace: true });
    },
    "open-event": () => openEvent(target.dataset.code || state.event.inviteCode),
    logout: () => {
      state.modal = { type: "logout" };
      state.drawer = false;
      renderOverlays();
    },
    "confirm-logout": () => {
      state.modal = null;
      navigate("home");
      showToast("Logged out of the mocked account");
    },
    "toggle-demo": () => setDemoMode(!demoMode),
    "start-onboarding": () => startOnboarding(),
    "toggle-genre": () => {
      const survey = state.onboarding;
      const key = target.dataset.genre;
      if (survey.genres.has(key)) survey.genres.delete(key);
      else if (survey.genres.size < survey.maxGenres) survey.genres.add(key);
      else return showToast(`Pick at most ${survey.maxGenres} genres`);
      render();
    },
    "onboarding-genres-done": () => saveOnboardingGenres(),
    "onboarding-skip": () => finishOnboarding("skipped"),
    "onboarding-done": () => finishOnboarding("complete"),
    "onboarding-retry": () => loadOnboarding(),
    "refresh-catalogue": () => bootstrapBackend(),
    "onboarding-continue": () => {
      state.onboarding.step = "round";
      loadOnboarding();
    },
    "survey-react": () => recordOnboardingReaction(target.dataset.reaction),
    "pick-reason": () => saveOnboardingReason(target.dataset.code, plainText(target.dataset.label)),
    "skip-reason": () => saveOnboardingReason(null, null),
    "toggle-sound": () => {
      soundOn = !soundOn;
      localStorage.setItem(SOUND_STORAGE_KEY, soundOn ? "1" : "0");
      applyClipSound();
    },
    "set-provider": async () => {
      const provider = target.dataset.provider;
      if (provider === state.provider) return;
      const previous = state.provider;
      state.provider = provider;
      render();
      try {
        const response = await fetch("/api/user/provider", {
          method: "PUT",
          headers: apiHeaders(),
          body: JSON.stringify({ provider }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || "Could not switch engine.");
        const label = provider === "nebius" ? "Qwen 3.5" : "Devin";
        showToast(
          payload.demo_mode
            ? `${label} selected — demo mode is on, so no engine is called`
            : payload.configured
              ? `Searching with ${label}`
              : `${provider === "nebius" ? "NEBIUS_API_KEY" : "DEVIN_API_KEY"} is missing on the server`,
        );
      } catch (error) {
        state.provider = previous;
        render();
        showToast(error instanceof Error ? error.message : "Could not switch engine.");
      }
    },
    "fake-edit": () => showToast("Name editing is outside this MVP"),
    "fake-delete": () => showToast("Account deletion is outside this MVP"),
  };
  handlers[action]?.();
});

const EVENT_ROUTES = new Set([
  "lobby",
  "round1-select",
  "wait-round1",
  "manage-round1",
  "wait-round2",
  "manage-round2",
  "finalists",
  "winner",
  "completed",
]);
let eventPollTimer = null;
let lastEventSignature = "";

function eventServer() {
  return state.event.server || {};
}

function guestName() {
  return localStorage.getItem("reelpick-display-name") || (userId === "demo-user" ? "Alex" : "Guest");
}

function startEventPolling() {
  if (eventPollTimer || !state.event.inviteCode) return;
  lastEventSignature = "";
  eventPollTimer = window.setInterval(refreshEventState, 2500);
}

function stopEventPolling() {
  window.clearInterval(eventPollTimer);
  eventPollTimer = null;
}

function inEventFlow() {
  return (
    EVENT_ROUTES.has(state.route) ||
    (state.route === "feed" && state.session.mode !== "personal")
  );
}

async function refreshEventState() {
  if (!state.event.inviteCode) return stopEventPolling();
  if (!inEventFlow()) return stopEventPolling();
  try {
    const response = await fetch(
      `/api/events/${encodeURIComponent(state.event.inviteCode)}/state`,
      { headers: apiHeaders() },
    );
    if (!response.ok) return;
    applyEventState(await response.json());
  } catch {
    /* keep the last known state until the next tick */
  }
}

function applyEventState(payload, { navigateOnChange = true } = {}) {
  const previousStatus = eventServer().status;
  const signature = JSON.stringify(payload);
  const unchanged = signature === lastEventSignature;
  lastEventSignature = signature;
  state.event.server = payload;
  state.event.id = payload.event_id;
  state.event.inviteCode = payload.invite_code;
  state.event.inviteUrl = payload.invite_url;
  state.event.name = payload.name;
  state.event.date = payload.event_date || "";
  state.event.prompt = payload.prompt;
  state.event.isHost = payload.is_host;
  state.event.round = payload.status;
  state.event.backendParticipants = payload.participants || [];
  state.event.nominations = new Set(payload.nominated_movie_ids || []);
  state.event.winner = payload.winner_movie_id || null;
  state.event.completed = payload.status === "completed";
  if (payload.my_nominations?.length) state.event.myPicks = new Set(payload.my_nominations);
  if (!navigateOnChange) return render();
  routeForEventState(previousStatus, payload, unchanged);
}

function renderEventUpdate(unchanged) {
  if (unchanged) return;
  if (state.route === "feed") return;
  render();
}

async function routeForEventState(previousStatus, payload, unchanged = false) {
  const changed = previousStatus !== payload.status;
  const iAmReady = (payload.participants || []).some(
    (participant) => participant.is_you && participant.ready,
  );

  if (payload.status === "completed") {
    if (state.route !== "winner" && state.route !== "completed") {
      return navigate("winner", { replace: true });
    }
    return renderEventUpdate(unchanged);
  }
  if (payload.status === "final") {
    if (payload.is_host) {
      if (state.route !== "finalists") return navigate("finalists", { replace: true });
    } else if (state.route !== "wait-round2") {
      return navigate("wait-round2", { replace: true });
    }
    return renderEventUpdate(unchanged);
  }
  if (payload.status === "round2") {
    if (iAmReady) {
      if (state.route !== "wait-round2" && state.route !== "manage-round2") {
        return navigate("wait-round2", { replace: true });
      }
      return renderEventUpdate(unchanged);
    }
    if (changed || (state.route === "lobby" && !payload.is_host)) {
      return startVotingRound();
    }
    return renderEventUpdate(unchanged);
  }
  if (payload.status === "round1") {
    if (iAmReady) {
      if (state.route !== "wait-round1" && state.route !== "manage-round1") {
        return navigate("wait-round1", { replace: true });
      }
      return renderEventUpdate(unchanged);
    }
    if (changed && !payload.is_host) return startRoundOneRecommendations();
    return renderEventUpdate(unchanged);
  }
  return renderEventUpdate(unchanged);
}

async function postEvent(path, body) {
  const response = await fetch(
    `/api/events/${encodeURIComponent(state.event.inviteCode)}${path}`,
    { method: "POST", headers: apiHeaders(), body: JSON.stringify(body) },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Movie night update failed.");
  return payload;
}

async function startVotingRound() {
  const ids = eventServer().nominated_movie_ids || [];
  if (ids.some((id) => !movieById[id])) await bootstrapBackend();
  const known = ids.filter((id) => movieById[id]);
  if (!known.length) return render();
  startFeed("round2", known);
}

async function loadInviteFromPath() {
  const match = window.location.pathname.match(/^\/join\/([A-Za-z0-9]+)$/);
  if (!match) return;
  const inviteCode = match[1].toUpperCase();
  state.event.inviteCode = inviteCode;
  try {
    const joinResponse = await fetch(`/api/events/${encodeURIComponent(inviteCode)}/join`, {
      method: "POST",
      headers: apiHeaders(),
      body: JSON.stringify({ display_name: guestName() }),
    });
    const joinPayload = await joinResponse.json().catch(() => ({}));
    if (!joinResponse.ok) throw new Error(joinPayload.detail || "Could not join movie night.");
    const stateResponse = await fetch(`/api/events/${encodeURIComponent(inviteCode)}/state`, {
      headers: apiHeaders(),
    });
    const payload = await stateResponse.json().catch(() => ({}));
    if (!stateResponse.ok) throw new Error(payload.detail || "Movie night not found.");
    navigate("lobby", { replace: true });
    applyEventState(payload);
    startEventPolling();
  } catch (error) {
    state.event.inviteCode = null;
    showToast(error instanceof Error ? error.message : "Movie night not found.");
  }
}

restoreLibrary();
render();
loadDemoClips().then(render);
bootstrapBackend();
loadInviteFromPath();
