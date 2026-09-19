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
  toast: "",
  loading: false,
  loadingMessage: "",
  homePrompt: "A funny movie like The Matrix, but lighter",
  preferenceTab: "liked",
  library: {
    liked: new Set(["everything-everywhere", "knives-out", "nice-guys"]),
    disliked: new Set(["game-night"]),
    watchlist: new Set(["about-time"]),
  },
  session: {
    mode: "personal",
    backendId: null,
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
    name: "Friday Movie Night",
    date: "2026-09-25",
    prompt: "Something funny, under two hours",
    round: "inviting",
    myPicks: new Set(),
    nominations: new Set(["palm-springs", "game-night", "nice-guys", "wilderpeople"]),
    winner: null,
    completed: false,
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

function apiHeaders(extra = {}) {
  return {
    "Content-Type": "application/json",
    "X-ReelPick-User": userId,
    ...extra,
  };
}

function catalogueMovie(movie) {
  const factual = movie.factual_metadata || {};
  return {
    id: movie.movie_id,
    title: safeText(movie.title),
    year: movie.year,
    poster: Number(factual.poster_sprite || 1),
    provider: movie.imdb_url ? "IMDb" : "JustWatch",
    genre: safeText(factual.genre || "Movie"),
    watch_url:
      movie.imdb_url ||
      `https://www.justwatch.com/us/search?q=${encodeURIComponent(plainText(movie.title))}`,
  };
}

function applyBootstrap(payload) {
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
    applyBootstrap(await response.json());
    render();
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
  render();
}

function goBack() {
  const previous = state.history.pop() || "home";
  state.route = previous;
  state.modal = null;
  state.actionMenu = null;
  render();
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

function poster(movie, extraClass = "") {
  return `<div class="poster poster--${movie.poster} ${extraClass}" role="img" aria-label="${movie.title} poster"></div>`;
}

function posterTile(movie, { action = "open-movie", selectable = false } = {}) {
  return `
    <article class="poster-tile" ${action ? `data-action="${action}" data-movie="${movie.id}"` : ""}>
      ${poster(movie)}
      <div class="${selectable ? "movie-tile__meta" : ""}">
        <div><h3>${movie.title}</h3><p>${movie.year}</p></div>
        ${selectable ? `<button class="overflow-button" data-action="movie-menu" data-movie="${movie.id}" aria-label="Movie actions">${icon("more", 17)}</button>` : ""}
      </div>
    </article>
  `;
}

function renderHome() {
  const recommendations = ["palm-springs", "knives-out", "everything-everywhere", "past-lives"].map((id) => movieById[id]);
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
      <div class="section-heading">
        <h2>Recommended for you</h2>
        <button class="text-button" data-action="preferences">Tune taste</button>
      </div>
      <div class="poster-strip">
        ${recommendations.map((movie) => posterTile(movie)).join("")}
      </div>
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
        <button class="drawer-link drawer-logout" data-action="logout">
          ${icon("logout", 18)} <span>Log out</span>
        </button>
      </aside>
    </div>
  `;
}

function renderAccount() {
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
      <div class="button-stack push-bottom">
        <button class="secondary-button" data-action="logout">${icon("logout", 17)} Log out</button>
        <button class="quiet-button" data-action="fake-delete">Delete account</button>
      </div>
    </section>
  `;
}

function renderPreferences() {
  const ids = [...state.library[state.preferenceTab]];
  const emptyCopy =
    state.preferenceTab === "liked"
      ? "Movies you like will appear here."
      : "Movies you dislike will appear here.";
  return `
    <section class="page">
      ${pageHeader("My Preferences")}
      <div class="tabs">
        <button class="tab ${state.preferenceTab === "liked" ? "tab--active" : ""}" data-action="pref-tab" data-tab="liked">Liked</button>
        <button class="tab ${state.preferenceTab === "disliked" ? "tab--active" : ""}" data-action="pref-tab" data-tab="disliked">Disliked</button>
      </div>
      ${
        ids.length
          ? `<div class="movie-grid">${ids.map((id) => posterTile(movieById[id], { action: "", selectable: true })).join("")}</div>`
          : `<div class="empty-state"><div><div class="empty-state__icon">${icon("heart", 28)}</div><h2>Nothing here yet</h2><p>${emptyCopy}</p><button class="primary-button" data-action="home">Find movies</button></div></div>`
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
                          <button class="small-button small-button--accent" data-action="where-to-watch" data-movie="${movie.id}">Where to watch</button>
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
      hook: safeText(recommendation.hook),
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
  state.loadingMessage = mode === "round1" ? "Building picks for your group…" : "Devin is finding your movies…";
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

async function startRoundOneRecommendations() {
  const result = await requestRecommendations({
    prompt: state.event.prompt,
    count: 5,
    mode: "round1",
    excludedIds: state.event.nominations,
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
      <div class="feed-clip poster--${movie.poster}" id="feedClip"></div>
      <header class="topbar topbar--feed">
        <button class="icon-button icon-button--ghost" data-action="exit-feed" aria-label="Exit feed">${icon("back")}</button>
        <h1 class="topbar__title">${state.session.index + 1}/${total}</h1>
        <div class="topbar__meta">${likedLabel}</div>
      </header>
      <div class="feed-guide"><span class="feed-guide__dot"></span>${isRoundTwo ? "Round 2" : "Hold to react"}</div>
      <div class="feed-copy">
        <h1>${movie.title}</h1>
        <p>${movie.year}</p>
        <div class="feed-hint"><span>↕</span> Swipe to browse · Hold and drag to choose</div>
      </div>
      <div class="clip-progress"></div>
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
                ${poster(movie)}
                <div class="selection-card__copy">
                  <h3>${movie.title}</h3>
                  <p>${movie.year}<br />${movie.genre}</p>
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
      <div class="final-poster">${poster(movie)}</div>
      <div class="final-copy">
        <p class="eyebrow">Tonight’s pick</p>
        <h1>${movie.title}</h1>
        <p>${movie.year} · ${movie.genre}</p>
      </div>
      <div class="button-stack push-bottom">
        <button class="primary-button" data-action="where-to-watch" data-movie="${movie.id}">Where to watch on ${movie.provider} ${icon("arrow", 17)}</button>
        ${state.library.watchlist.has(movie.id) ? "" : '<button class="secondary-button" data-action="save-chosen">Save to Watchlist</button>'}
        <button class="quiet-button" data-action="home">Start over</button>
      </div>
    </section>
  `;
}

function renderNights() {
  const status = eventStatus();
  return `
    <section class="page page--flex">
      ${pageHeader("Movie Nights")}
      <button class="primary-button" style="margin-top:22px" data-action="create-event">${icon("users", 18)} Host a movie night</button>
      <div class="section-heading"><h2>Hosting</h2></div>
      <div class="event-list">
        <button class="event-card" data-action="open-event">
          <div class="event-card__top">
            <div><h3>${state.event.name}</h3><p>${formatDate(state.event.date)} · Hosted by you</p></div>
            <span class="status-pill status-pill--orange">${status}</span>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between">
            <div class="avatars">
              <span class="avatar">AS</span><span class="avatar" style="background:var(--blue)">MI</span><span class="avatar" style="background:var(--green)">NO</span>
              <span class="avatars__count">4 people</span>
            </div>
            ${icon("chevron", 18)}
          </div>
        </button>
      </div>
      <div class="section-heading"><h2>Joined</h2></div>
      <div class="status-card" style="padding:17px;color:var(--muted);font-size:11px">Movie nights you join will appear here.</div>
    </section>
  `;
}

function eventStatus() {
  if (state.event.completed) return "Completed";
  const labels = {
    inviting: "Inviting",
    round1: "Round 1 · Choosing",
    waiting1: "Round 1 · 4 of 5 ready",
    round2: "Round 2 · Voting",
    waiting2: "Waiting for host",
    final: "Final choice",
    winner: "Tonight’s movie",
  };
  return labels[state.event.round] || "Inviting";
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
  const statuses = {
    lobby: ["Host", "Joined", "Joined", "Waiting"],
    round1: ["Ready", "Ready", "Choosing", "Ready"],
    round2: ["Finished", "Finished", "Voting", "Not started"],
  }[stage];
  return [
    ["AS", "Alex", statuses[0], "var(--orange)"],
    ["MI", "Mia", statuses[1], "var(--blue)"],
    ["NO", "Noah", statuses[2], "var(--green)"],
    ["JO", "Jo", statuses[3], "var(--amber)"],
  ];
}

function participantList(stage) {
  return participants(stage)
    .map(
      ([initials, name, status, color], index) => `
        <div class="participant">
          <span class="avatar" style="background:${color};${color === "var(--amber)" ? "color:var(--ink)" : ""}">${initials}</span>
          <span><strong>${name}${index === 0 ? " · Host" : ""}</strong><small>${index === 0 ? "Created this movie night" : "Joined by link"}</small></span>
          <span class="participant__status">${status}</span>
        </div>
      `,
    )
    .join("");
}

function renderLobby() {
  const inviteUrl = safeText(state.event.inviteUrl || "Invite link is being created…");
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
      <div class="section-heading"><h2>4 participants</h2><span style="font-size:9px;color:var(--muted)">You’re the host</span></div>
      <div class="participant-list">${participantList("lobby")}</div>
      <div class="button-stack push-bottom">
        <button class="primary-button" data-action="start-round1">Start choosing ${icon("arrow", 17)}</button>
        <button class="secondary-button" data-action="manage-event">Manage event</button>
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
  return `
    <section class="page page--flex">
      ${pageHeader(state.event.name, { right: "Round 1" })}
      ${waitingVisual("4/5", "people ready")}
      <div class="waiting-copy">
        <h1>Your picks are in.</h1>
        <p>One person is still choosing. We’ll keep your nominations hidden until the host closes the round.</p>
      </div>
      <div class="button-stack push-bottom">
        <button class="primary-button" data-action="manage-round1">Open host controls</button>
        <button class="secondary-button" data-action="edit-picks">Edit my picks</button>
      </div>
    </section>
  `;
}

function renderManageRound1() {
  const inviteUrl = safeText(state.event.inviteUrl || "Invite link unavailable");
  return `
    <section class="page page--flex">
      ${pageHeader("Manage Round 1")}
      <p class="eyebrow" style="margin-top:26px">${state.event.name}</p>
      <h1 class="display-title display-title--small">Nominations<br /><span class="accent">are coming in.</span></h1>
      <div class="round-summary">
        <div class="round-stat"><strong>4/5</strong><span>ready</span></div>
        <div class="round-stat"><strong>7</strong><span>submissions</span></div>
        <div class="round-stat"><strong>4</strong><span>people</span></div>
      </div>
      <div class="section-heading"><h2>Participants</h2></div>
      <div class="participant-list">${participantList("round1")}</div>
      <div class="invite-card">
        <span class="invite-card__label">Invite link</span>
        <div class="invite-card__link"><code>${inviteUrl}</code><button class="small-button" data-action="copy-link">${icon("copy", 14)}</button><span></span></div>
      </div>
      <div class="push-bottom">
        <button class="primary-button" data-action="close-round1">Close Round 1</button>
      </div>
    </section>
  `;
}

function renderWaitRound2() {
  return `
    <section class="page page--flex">
      ${pageHeader(state.event.name, { right: "Round 2" })}
      ${waitingVisual("3/4", "votes finished")}
      <div class="waiting-copy">
        <h1>Your votes are in.</h1>
        <p>Results stay hidden until the host closes voting. One person is still making their way through the shortlist.</p>
      </div>
      <div class="push-bottom">
        <button class="primary-button" data-action="manage-round2">Open host controls</button>
      </div>
    </section>
  `;
}

function renderManageRound2() {
  return `
    <section class="page page--flex">
      ${pageHeader("Manage Round 2")}
      <p class="eyebrow" style="margin-top:26px">${state.event.name}</p>
      <h1 class="display-title display-title--small">Voting is<br /><span class="accent">almost done.</span></h1>
      <div class="round-summary">
        <div class="round-stat"><strong>6</strong><span>movies</span></div>
        <div class="round-stat"><strong>4</strong><span>voters</span></div>
        <div class="round-stat"><strong>3/4</strong><span>finished</span></div>
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
  return [movieById["palm-springs"], movieById["nice-guys"]];
}

function renderFinalists() {
  return `
    <section class="page page--flex">
      ${pageHeader("Final choice")}
      <p class="eyebrow" style="margin-top:28px">Host decision</p>
      <h1 class="display-title display-title--small">Choose tonight’s<br /><span class="accent">movie.</span></h1>
      <p class="lede">The room narrowed six nominations to these final two. The last call is yours.</p>
      <div class="finalist-grid">
        ${finalists()
          .map(
            (movie, index) => `
              <article class="finalist-card">
                ${poster(movie)}
                <div class="finalist-card__copy">
                  <h3>${movie.title}</h3>
                  <p>${movie.year}<br />${index === 0 ? "4 likes · 1 dislike" : "3 likes · 0 dislikes"}</p>
                  <button class="small-button small-button--accent" data-action="select-winner" data-movie="${movie.id}">Choose this movie</button>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="status-card" style="margin-top:14px;padding:14px;font-size:10px;color:var(--muted)">
        Ranked by likes, then fewest dislikes, then number of nominations.
      </div>
    </section>
  `;
}

function renderWinner() {
  const movie = movieById[state.event.winner || "palm-springs"];
  return `
    <section class="page page--flex" style="position:relative">
      ${pageHeader("Tonight’s movie")}
      <div class="winner-confetti"><span></span><span></span><span></span><span></span><span></span></div>
      <div class="final-poster" style="position:relative">${poster(movie)}</div>
      <div class="final-copy" style="position:relative">
        <p class="eyebrow">The room has spoken</p>
        <h1>${movie.title}</h1>
        <p>${movie.year} · Chosen by Alex</p>
      </div>
      <div class="status-card" style="margin-top:20px;padding:14px;text-align:center">
        <strong style="font-size:11px">${state.event.name}</strong>
        <p style="margin:4px 0 0;color:var(--muted);font-size:9px">${formatDate(state.event.date)} · 4 participants</p>
      </div>
      <div class="button-stack push-bottom">
        <button class="primary-button" data-action="where-to-watch" data-movie="${movie.id}">Where to watch on ${movie.provider} ${icon("arrow", 17)}</button>
        <button class="secondary-button" data-action="end-night">End movie night</button>
      </div>
    </section>
  `;
}

function renderCompleted() {
  const movie = movieById[state.event.winner || "palm-springs"];
  return `
    <section class="page page--flex">
      ${pageHeader("Completed movie night")}
      <p class="eyebrow" style="margin-top:28px">Completed</p>
      <h1 class="display-title display-title--small">${state.event.name}</h1>
      <p class="lede">${formatDate(state.event.date)} · Hosted by Alex · 4 participants</p>
      <div class="selection-card" style="margin-top:24px">
        ${poster(movie)}
        <div class="selection-card__copy">
          <p class="eyebrow" style="margin:0 0 8px">Winning movie</p>
          <h3>${movie.title}</h3>
          <p>${movie.year} · ${movie.genre}</p>
          <button class="small-button small-button--accent" data-action="where-to-watch" data-movie="${movie.id}">Where to watch</button>
        </div>
      </div>
      <div class="section-heading"><h2>Finalists</h2></div>
      <div class="poster-strip" style="margin:0">${finalists().map((item) => posterTile(item, { action: "" })).join("")}</div>
      <div class="push-bottom"><button class="secondary-button" data-action="nights">Back to Movie Nights</button></div>
    </section>
  `;
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
            <div><p class="eyebrow" style="margin:0 0 5px">Recommended for you</p><h2 style="font-size:20px">${movie.title}</h2><p style="margin:4px 0 0">${movie.year} · ${movie.genre}</p></div>
          </div>
          <div class="button-stack">
            <button class="primary-button" data-action="where-to-watch" data-movie="${movie.id}">Where to watch on ${movie.provider}</button>
            <button class="secondary-button" data-action="quick-save" data-movie="${movie.id}">${state.library.watchlist.has(movie.id) ? "Remove from Watchlist" : "Save to Watchlist"}</button>
          </div>
        </div>
      </div>
    `;
  }
  const confirmation = {
    close1: {
      title: "Close Round 1?",
      copy: "One person hasn’t locked in their movies. Close the round anyway?",
      confirm: "confirm-close1",
      button: "Close Round 1",
    },
    close2: {
      title: "Close Round 2?",
      copy: "One person hasn’t finished voting. Close the round anyway?",
      confirm: "confirm-close2",
      button: "Close Round 2",
    },
    winner: {
      title: `Choose “${movieById[state.modal.movieId].title}”?`,
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
    actions =
      state.preferenceTab === "liked"
        ? [
            ["remove-preference", "Remove from preferences"],
            ["move-disliked", "Move to disliked"],
            ["add-watchlist", "Add to Watchlist"],
          ]
        : [
            ["remove-preference", "Remove from preferences"],
            ["move-liked", "Move to liked"],
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
  document.querySelector(".modal-shade")?.remove();
  document.querySelector(".action-menu")?.remove();
  document.querySelector(".loading-shade")?.remove();
  document.querySelector(".toast")?.remove();
  const loading = state.loading
    ? `<div class="loading-shade" role="status"><div class="loading-card"><span class="loading-spinner"></span><strong>${state.loadingMessage}</strong><p>This can take a minute.</p></div></div>`
    : "";
  app.insertAdjacentHTML(
    "beforeend",
    renderDrawer() +
      renderModal() +
      renderActionMenu() +
      loading +
      (state.toast ? `<div class="toast">${state.toast}</div>` : ""),
  );
}

function render() {
  const routes = {
    home: renderHome,
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
  await submitFeedback(movieId, "watched_rating", rating, {
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
  if (state.session.mode === "round2") navigate("wait-round2", { replace: true });
}

function bindFeedGestures() {
  const surface = document.querySelector("#feedSurface");
  if (!surface) return;
  surface.addEventListener("pointerdown", onPointerDown);
  surface.addEventListener("pointermove", onPointerMove);
  surface.addEventListener("pointerup", onPointerUp);
  surface.addEventListener("pointercancel", onPointerCancel);
  surface.addEventListener("contextmenu", (event) => event.preventDefault());
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
  else document.querySelector("#feedClip")?.classList.toggle("paused");
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

function openEventRoute() {
  if (state.event.completed) return navigate("completed");
  const routeByRound = {
    inviting: "lobby",
    round1: "lobby",
    waiting1: "wait-round1",
    round2: "wait-round2",
    waiting2: "wait-round2",
    final: "finalists",
    winner: "winner",
  };
  navigate(routeByRound[state.event.round] || "lobby");
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
  if (simpleRoutes.includes(action)) return navigate(action);
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
    voice: () => showToast("Voice input is mocked for the demo"),
    "open-movie": () => {
      state.modal = { type: "movie", movieId };
      renderOverlays();
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
    "pref-tab": () => {
      state.preferenceTab = target.dataset.tab;
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
    "exit-feed": () => {
      if (state.session.mode === "personal") navigate("home");
      else navigate("lobby");
    },
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
      } catch (error) {
        showToast(error instanceof Error ? error.message : "Could not create movie night.");
        return;
      } finally {
        state.loading = false;
        state.loadingMessage = "";
      }
      navigate("lobby");
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
    "start-round1": () => {
      startRoundOneRecommendations();
    },
    "toggle-nomination": () => {
      if (state.event.myPicks.has(movieId)) state.event.myPicks.delete(movieId);
      else if (state.event.myPicks.size < 2) state.event.myPicks.add(movieId);
      else return showToast("You can nominate up to two movies");
      render();
    },
    "lock-picks": () => {
      state.event.myPicks.forEach((id) => state.event.nominations.add(id));
      state.event.round = "waiting1";
      navigate("wait-round1");
    },
    "edit-picks": () => navigate("round1-select"),
    "manage-round1": () => navigate("manage-round1"),
    "close-round1": () => {
      state.modal = { type: "close1" };
      renderOverlays();
    },
    "confirm-close1": () => {
      state.modal = null;
      state.event.round = "round2";
      const ids = [...new Set([...state.event.nominations, ...state.event.myPicks])].slice(0, 6);
      while (ids.length < 4) ids.push(movies[ids.length].id);
      startFeed("round2", ids);
    },
    "manage-round2": () => navigate("manage-round2"),
    "close-round2": () => {
      state.modal = { type: "close2" };
      renderOverlays();
    },
    "confirm-close2": () => {
      state.modal = null;
      state.event.round = "final";
      navigate("finalists");
    },
    "select-winner": () => {
      state.modal = { type: "winner", movieId };
      renderOverlays();
    },
    "confirm-winner": () => {
      state.event.winner = movieId;
      state.event.round = "winner";
      state.modal = null;
      navigate("winner");
    },
    "end-night": () => {
      state.event.completed = true;
      state.event.round = "completed";
      navigate("completed");
    },
    "open-event": openEventRoute,
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
    "fake-edit": () => showToast("Name editing is outside this MVP"),
    "fake-delete": () => showToast("Account deletion is outside this MVP"),
  };
  handlers[action]?.();
});

async function loadInviteFromPath() {
  const match = window.location.pathname.match(/^\/join\/([A-Za-z0-9]+)$/);
  if (!match) return;
  const inviteCode = match[1];
  try {
    const eventResponse = await fetch(`/api/events/${encodeURIComponent(inviteCode)}`, {
      headers: apiHeaders(),
    });
    const eventPayload = await eventResponse.json().catch(() => ({}));
    if (!eventResponse.ok) throw new Error(eventPayload.detail || "Movie night not found.");
    await fetch(`/api/events/${encodeURIComponent(inviteCode)}/join`, {
      method: "POST",
      headers: apiHeaders(),
      body: JSON.stringify({ display_name: "Guest" }),
    });
    state.event.id = eventPayload.event_id;
    state.event.inviteCode = eventPayload.invite_code;
    state.event.inviteUrl = eventPayload.invite_url;
    state.event.name = eventPayload.name;
    state.event.date = eventPayload.event_date || "";
    state.event.prompt = eventPayload.prompt;
    state.event.round = eventPayload.status || "inviting";
    navigate("lobby", { replace: true });
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Movie night not found.");
  }
}

restoreLibrary();
render();
bootstrapBackend();
loadInviteFromPath();
