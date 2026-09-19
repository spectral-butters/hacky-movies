const flowData = {
  solo: [
    {
      label: "Prompt",
      description: "Say what you want in natural language.",
      render: renderSoloPrompt,
    },
    {
      label: "AI match",
      description: "The agent combines the prompt with taste history.",
      render: renderMatching,
    },
    {
      label: "5 shorts",
      description: "A five-card vertical feed captures fast reactions.",
      render: renderReel,
    },
    {
      label: "Taste recap",
      description: "The model explains what worked and offers a refinement.",
      render: renderRecap,
    },
    {
      label: "2 refined",
      description: "Two sharper recommendations close the decision loop.",
      render: renderRefined,
    },
    {
      label: "Watch",
      description: "Choose a provider and leave the app ready to play.",
      render: () => renderWinner(false),
    },
  ],
  group: [
    {
      label: "Lobby",
      description: "Create a room and bring everyone in with one code.",
      render: renderLobby,
    },
    {
      label: "Set vibe",
      description: "The host sets shared constraints before private picks.",
      render: renderGroupPrompt,
    },
    {
      label: "Pick 2",
      description: "Each person privately shortlists up to two movies.",
      render: renderGroupPicks,
    },
    {
      label: "Ready up",
      description: "The room waits until every personal shortlist is locked.",
      render: renderWaiting,
    },
    {
      label: "Vote",
      description: "Everyone votes once across the combined shortlist.",
      render: renderBallot,
    },
    {
      label: "Results",
      description: "A transparent reveal gets the group to consensus.",
      render: renderResults,
    },
    {
      label: "Winner",
      description: "The winning movie links straight to a provider.",
      render: () => renderWinner(true),
    },
  ],
};

const state = {
  mode: "solo",
  index: 0,
  soloPrompt: "",
  groupPrompt: "",
  selectedPicks: new Set([0]),
  vote: null,
};

const appScreen = document.querySelector("#appScreen");
const screenNav = document.querySelector("#screenNav");
const description = document.querySelector("#screenDescription");
const prevButton = document.querySelector("#prevButton");
const nextButton = document.querySelector("#nextButton");

function appHeader({ back = false, right = "◌" } = {}) {
  return `
    <div class="app-header">
      <div class="app-wordmark"><span>S</span> SCENE</div>
      <button class="round-button" aria-label="${back ? "Go back" : "Profile"}">${back ? "←" : right}</button>
    </div>
  `;
}

function renderSoloPrompt() {
  return `
    <section class="screen">
      ${appHeader()}
      <p class="screen-label">Tonight's mission</p>
      <h2 class="screen-title">What are you<br />in the mood for?</h2>
      <p class="screen-subtitle">Describe a feeling, a movie, or the kind of night you're having.</p>
      <div class="prompt-box">
        <textarea id="soloPrompt" aria-label="Movie prompt" placeholder="A clever sci-fi thriller, like The Matrix, but not too dark...">${state.soloPrompt}</textarea>
        <div class="prompt-tools">
          <button class="voice-button" aria-label="Use voice">⌁</button>
          <button class="go-button" data-next>Find my 5 <span>→</span></button>
        </div>
      </div>
      <p class="suggestion-label">Try one</p>
      <div class="suggestions">
        <button class="suggestion" data-prompt="Funny, warm, under 2 hours">Funny + feel-good</button>
        <button class="suggestion" data-prompt="A mind-bender like The Matrix">Like The Matrix</button>
        <button class="suggestion" data-prompt="A tense thriller with no gore">Tense, no gore</button>
      </div>
      <div class="taste-memory">
        <div class="mini-avatars">
          <span class="mini-avatar">SF</span>
          <span class="mini-avatar">♥</span>
          <span class="mini-avatar">12</span>
        </div>
        <p><strong>Your taste is switched on.</strong><br />Using 12 past reactions to tune results.</p>
      </div>
    </section>
  `;
}

function renderMatching() {
  return `
    <section class="screen matching-screen">
      ${appHeader({ back: true })}
      <div class="matching-visual">
        <div class="orbit"></div>
        <div class="orbit orbit--inner"></div>
        <div class="match-stack">
          <div class="match-card"></div>
          <div class="match-card"></div>
          <div class="match-card"></div>
        </div>
      </div>
      <div class="matching-copy">
        <h2>Reading the room...</h2>
        <p>Balancing pace, humor and your recent likes</p>
        <div class="scan-line"></div>
      </div>
      <button class="primary-button" data-next>See my 5 matches</button>
    </section>
  `;
}

function renderReel() {
  return `
    <section class="screen reel-screen">
      <div class="reel-backdrop"></div>
      <div class="reel-top">
        <div class="reel-progress">
          <span class="active"></span><span></span><span></span><span></span><span></span>
        </div>
        <div class="reel-meta-top">
          <span class="for-you-pill">✦ Picked for you</span>
          <span class="count-pill">1 / 5</span>
        </div>
      </div>
      <div class="sound-pill"><span class="sound-bars">▮▮▮</span> AI scene guide · on</div>
      <div class="reel-actions">
        <button class="reel-action" data-action="Love it">
          <span class="reel-action-icon">♥</span><span>Love</span>
        </button>
        <button class="reel-action" data-action="Saved">
          <span class="reel-action-icon">＋</span><span>Later</span>
        </button>
        <button class="reel-action" data-action="Not for me">
          <span class="reel-action-icon">×</span><span>Pass</span>
        </button>
        <button class="reel-action" data-action="Seen it">
          <span class="reel-action-icon">✓</span><span>Seen</span>
        </button>
      </div>
      <div class="reel-copy">
        <div class="movie-kicker">93% taste match</div>
        <h2>Palm Springs</h2>
        <div class="movie-meta"><span>2020</span><span>1h 30m</span><span>Comedy · Sci-fi</span></div>
        <p class="match-reason">A time-loop comedy that stays sharp, warm and gloriously weird.</p>
        <p class="caption">“What if today was the only day — forever?”</p>
      </div>
      <div class="action-toast" id="actionToast"></div>
    </section>
  `;
}

function renderRecap() {
  return `
    <section class="screen screen--light recap-screen">
      ${appHeader({ back: true })}
      <p class="screen-label">Your taste, decoded</p>
      <h2 class="screen-title">You liked 3<br />out of 5.</h2>
      <div class="recap-count">
        <strong>3<span style="color:#93b910">/5</span></strong>
        <p>Strong signal<br />for tonight</p>
      </div>
      <div class="poster-row">
        <article class="mini-poster"><p>Palm<br />Springs</p></article>
        <article class="mini-poster"><p>Game<br />Night</p></article>
        <article class="mini-poster"><p>The Nice<br />Guys</p></article>
      </div>
      <div class="taste-analysis">
        <div class="taste-analysis-header"><span class="spark">✦</span> What connected</div>
        <h3>Fast, funny stories with chemistry — not spectacle.</h3>
        <div class="trait-row">
          <span class="trait">quick dialogue</span>
          <span class="trait">clever premise</span>
          <span class="trait">warm ending</span>
        </div>
      </div>
      <div class="button-stack">
        <button class="primary-button dark" data-next>Use this to find 2 better matches</button>
        <button class="secondary-button" data-screen="2">Replay my 5</button>
      </div>
    </section>
  `;
}

function renderRefined() {
  return `
    <section class="screen">
      ${appHeader({ back: true })}
      <p class="screen-label">Refined from your reactions</p>
      <h2 class="screen-title">Two strong<br />finalists.</h2>
      <p class="screen-subtitle">Both hit the same notes as your three likes — with less of what you skipped.</p>
      <div class="refined-cards">
        <article class="refined-card">
          <span class="refined-card-number">1</span>
          <div class="refined-card-content">
            <h3>About Time</h3>
            <p>Witty time travel with a genuinely warm center.</p>
            <button class="tiny-link" data-next>Choose this →</button>
          </div>
        </article>
        <article class="refined-card">
          <span class="refined-card-number">2</span>
          <div class="refined-card-content">
            <h3>Safety Not Guaranteed</h3>
            <p>Offbeat sci-fi, grounded by great chemistry.</p>
            <button class="tiny-link" data-next>Choose this →</button>
          </div>
        </article>
      </div>
    </section>
  `;
}

function renderWinner(isGroup) {
  const title = isGroup ? "Palm Springs" : "About Time";
  const match = isGroup ? "4 friends chose this" : "96% final match";
  const copy = isGroup
    ? "Fast, funny and crowd-friendly. Your group picked something nobody has seen."
    : "You wanted clever, funny and warm. This is the one.";

  return `
    <section class="screen winner-screen">
      <div class="winner-hero"></div>
      <div class="winner-content">
        <span class="winner-match">✦ ${match}</span>
        <h2>${title}</h2>
        <div class="movie-meta"><span>${isGroup ? "2020" : "2013"}</span><span>${isGroup ? "1h 30m" : "2h 3m"}</span><span>Comedy · Romance · Sci-fi</span></div>
        <p>${copy}</p>
        <div class="watch-options">
          <span class="watch-provider">${isGroup ? "Hulu" : "Netflix"}</span>
          <span class="watch-provider">Prime · Rent</span>
          <span class="watch-provider">Apple TV</span>
        </div>
        <div class="button-stack">
          <button class="primary-button">Watch now ↗</button>
          <button class="secondary-button" data-restart>Start a new search</button>
        </div>
      </div>
    </section>
  `;
}

function renderLobby() {
  return `
    <section class="screen group-lobby">
      ${appHeader()}
      <p class="screen-label">Group night</p>
      <h2 class="screen-title">Pick together.<br />No group chat chaos.</h2>
      <p class="screen-subtitle">Everyone contributes two favorites. Then the room votes.</p>
      <div class="group-code-card">
        <div class="group-code-label">Invite code</div>
        <div class="group-code">7K4M <button class="copy-chip">Copy link</button></div>
      </div>
      <div class="member-list">
        <div class="member"><span class="avatar">AL</span><div class="member-copy"><strong>Alex</strong><span>Host</span></div><span class="ready-state">Ready</span></div>
        <div class="member"><span class="avatar">MI</span><div class="member-copy"><strong>Mia</strong><span>Joined just now</span></div><span class="ready-state">Ready</span></div>
        <div class="member"><span class="avatar">NO</span><div class="member-copy"><strong>Noah</strong><span>Choosing a name...</span></div><span class="waiting-state">Joining</span></div>
        <div class="member"><span class="avatar">+</span><div class="member-copy"><strong>Waiting for friends</strong><span>Share code 7K4M</span></div><span class="waiting-state">Open</span></div>
      </div>
      <div class="button-stack">
        <button class="primary-button" data-next>Set the group vibe</button>
      </div>
    </section>
  `;
}

function renderGroupPrompt() {
  return `
    <section class="screen">
      ${appHeader({ back: true })}
      <p class="screen-label">Shared brief</p>
      <h2 class="screen-title">What works<br />for everyone?</h2>
      <p class="screen-subtitle">Set the guardrails once. Personal taste still shapes each person's feed.</p>
      <div class="prompt-box">
        <textarea id="groupPrompt" aria-label="Group movie prompt" placeholder="Funny, under 2 hours, nothing too heavy...">${state.groupPrompt}</textarea>
        <div class="prompt-tools">
          <button class="voice-button" aria-label="Use voice">⌁</button>
          <button class="go-button" data-next>Build feeds <span>→</span></button>
        </div>
      </div>
      <p class="suggestion-label">Quick guardrails</p>
      <div class="suggestions">
        <button class="suggestion" data-group-prompt="Funny, under 2 hours, nothing too heavy">Under 2 hours</button>
        <button class="suggestion" data-group-prompt="Something nobody in the group has watched">Nobody's seen it</button>
        <button class="suggestion" data-group-prompt="Crowd-pleasing but not obvious">Not too obvious</button>
      </div>
      <div class="taste-memory">
        <div class="mini-avatars">
          <span class="mini-avatar">AL</span>
          <span class="mini-avatar">MI</span>
          <span class="mini-avatar">NO</span>
        </div>
        <p><strong>3 taste profiles connected.</strong><br />Each feed will feel personal.</p>
      </div>
    </section>
  `;
}

function renderGroupPicks() {
  const movies = [
    ["Palm Springs", "Mia's feed · 93%"],
    ["Game Night", "Alex's feed · 91%"],
    ["The Nice Guys", "Noah's feed · 89%"],
    ["Hunt for the Wilderpeople", "Alex's feed · 87%"],
  ];
  return `
    <section class="screen">
      ${appHeader({ back: true })}
      <p class="screen-label">Private round · Alex</p>
      <h2 class="screen-title">Bring your<br />best two.</h2>
      <p class="screen-subtitle">Your picks stay private until everyone locks in.</p>
      <div class="pick-grid">
        ${movies
          .map(
            ([title, meta], index) => `
              <article class="pick-card ${state.selectedPicks.has(index) ? "selected" : ""}" data-pick="${index}">
                <div class="pick-card-copy"><h3>${title}</h3><p>${meta}</p></div>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="selection-counter">
        <span><strong>${state.selectedPicks.size}</strong> of 2 selected</span>
        <button class="go-button" data-next ${state.selectedPicks.size === 0 ? "disabled" : ""}>Lock picks →</button>
      </div>
    </section>
  `;
}

function renderWaiting() {
  return `
    <section class="screen matching-screen">
      ${appHeader({ back: true })}
      <div class="wait-visual">
        <div class="wait-ring">
          <span class="avatar-bubble">AL</span>
          <span class="avatar-bubble">MI</span>
          <span class="avatar-bubble">NO</span>
          <span class="avatar-bubble">JO</span>
          <span class="avatar-bubble">•••</span>
          <div class="wait-center"><strong>6 picks</strong><span>from 4 people</span></div>
        </div>
      </div>
      <div class="wait-copy">
        <h2>Everyone's locked in.</h2>
        <p>Duplicates are merged. Watched titles are removed before the vote.</p>
      </div>
      <button class="primary-button" data-next>Reveal the shortlist</button>
    </section>
  `;
}

function renderBallot() {
  const movies = [
    ["Palm Springs", "Comedy · Sci-fi"],
    ["Game Night", "Comedy · Mystery"],
    ["The Nice Guys", "Comedy · Crime"],
    ["Hunt for the Wilderpeople", "Adventure · Comedy"],
  ];
  return `
    <section class="screen">
      ${appHeader({ back: true })}
      <p class="screen-label">Final vote</p>
      <h2 class="screen-title">One vote.<br />Make it count.</h2>
      <p class="screen-subtitle">Tap a title to watch its 20-second hook. Vote when you're ready.</p>
      <div class="ballot">
        ${movies
          .map(
            ([title, meta], index) => `
              <article class="ballot-row ${state.vote === index ? "voted" : ""}" data-vote="${index}">
                <span class="ballot-thumb"></span>
                <div class="ballot-copy"><strong>${title}</strong><span>${meta}</span></div>
                <span class="vote-button">${state.vote === index ? "✓" : "▶"}</span>
              </article>
            `,
          )
          .join("")}
      </div>
      <p class="vote-note">Votes reveal only when everyone is done — no bandwagon effect.</p>
      <button class="primary-button" style="margin-top:12px" data-next>Lock my vote</button>
    </section>
  `;
}

function renderResults() {
  const rows = [
    ["Palm Springs", "3 votes", 100, ["AL", "MI"]],
    ["Game Night", "1 vote", 38, ["NO"]],
    ["The Nice Guys", "0 votes", 10, []],
    ["Hunt for the Wilderpeople", "0 votes", 10, []],
  ];
  return `
    <section class="screen">
      ${appHeader({ back: true })}
      <p class="screen-label">The room has spoken</p>
      <h2 class="screen-title">We have<br />a winner.</h2>
      <div class="result-card"><p>Top pick · 75% of the room</p><h3>Palm Springs</h3></div>
      <div class="results-list">
        ${rows
          .map(
            ([title, votes, width, voters], index) => `
              <div class="result-row">
                <span class="result-rank">${index + 1}</span>
                <div class="result-info">
                  <div class="result-copy"><strong>${title}</strong><span>${votes}</span></div>
                  <div class="result-track"><div class="result-bar" style="width:${width}%"></div></div>
                </div>
                <div class="voter-stack">${voters.map((voter) => `<span>${voter}</span>`).join("")}</div>
              </div>
            `,
          )
          .join("")}
      </div>
      <button class="primary-button" style="margin-top:22px" data-next>See where to watch</button>
    </section>
  `;
}

function bindScreenInteractions() {
  appScreen.querySelectorAll("[data-next]").forEach((button) => {
    button.addEventListener("click", () => goTo(state.index + 1));
  });

  appScreen.querySelectorAll("[data-restart]").forEach((button) => {
    button.addEventListener("click", restart);
  });

  appScreen.querySelectorAll("[data-screen]").forEach((button) => {
    button.addEventListener("click", () => goTo(Number(button.dataset.screen)));
  });

  appScreen.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      state.soloPrompt = button.dataset.prompt;
      render();
      document.querySelector("#soloPrompt")?.focus();
    });
  });

  appScreen.querySelectorAll("[data-group-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      state.groupPrompt = button.dataset.groupPrompt;
      render();
      document.querySelector("#groupPrompt")?.focus();
    });
  });

  document.querySelector("#soloPrompt")?.addEventListener("input", (event) => {
    state.soloPrompt = event.target.value;
  });

  document.querySelector("#groupPrompt")?.addEventListener("input", (event) => {
    state.groupPrompt = event.target.value;
  });

  appScreen.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      appScreen.querySelectorAll("[data-action]").forEach((item) => item.classList.remove("selected"));
      button.classList.add("selected");
      const toast = document.querySelector("#actionToast");
      toast.textContent = button.dataset.action;
      toast.classList.remove("show");
      void toast.offsetWidth;
      toast.classList.add("show");
    });
  });

  appScreen.querySelectorAll("[data-pick]").forEach((card) => {
    card.addEventListener("click", () => {
      const value = Number(card.dataset.pick);
      if (state.selectedPicks.has(value)) {
        state.selectedPicks.delete(value);
      } else if (state.selectedPicks.size < 2) {
        state.selectedPicks.add(value);
      }
      render();
    });
  });

  appScreen.querySelectorAll("[data-vote]").forEach((row) => {
    row.addEventListener("click", () => {
      state.vote = Number(row.dataset.vote);
      render();
    });
  });
}

function renderNav() {
  const screens = flowData[state.mode];
  screenNav.innerHTML = screens
    .map(
      (screen, index) =>
        `<button class="screen-dot ${index === state.index ? "active" : ""}" data-nav="${index}">${screen.label}</button>`,
    )
    .join("");

  screenNav.querySelectorAll("[data-nav]").forEach((button) => {
    button.addEventListener("click", () => goTo(Number(button.dataset.nav)));
  });
}

function render() {
  const screens = flowData[state.mode];
  const current = screens[state.index];
  appScreen.innerHTML = current.render();
  description.textContent = current.description;
  prevButton.disabled = state.index === 0;
  nextButton.disabled = state.index === screens.length - 1;
  renderNav();
  bindScreenInteractions();
}

function goTo(index) {
  const max = flowData[state.mode].length - 1;
  state.index = Math.max(0, Math.min(index, max));
  render();
}

function restart() {
  state.index = 0;
  state.vote = null;
  state.selectedPicks = new Set([0]);
  render();
}

document.querySelectorAll("[data-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-mode]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.mode = button.dataset.mode;
    state.index = 0;
    render();
  });
});

prevButton.addEventListener("click", () => goTo(state.index - 1));
nextButton.addEventListener("click", () => goTo(state.index + 1));
document.querySelector("#restartButton").addEventListener("click", restart);

document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") goTo(state.index - 1);
  if (event.key === "ArrowRight") goTo(state.index + 1);
});

render();
