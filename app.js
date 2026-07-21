const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const renderList = (items = []) => `<ul>${items.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;

async function loadJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} konnte nicht geladen werden.`);
  return response.json();
}

function renderEntries(entries) {
  const container = document.querySelector("#entries");
  const ledger = document.querySelector("#decision-ledger");

  container.innerHTML = entries.map((entry, index) => `
    <article class="entry-card" id="${escapeHtml(entry.slug)}">
      <aside class="entry-meta">
        <span class="entry-number">${String(index + 1).padStart(2, "0")}</span>
        <time class="entry-date" datetime="${escapeHtml(entry.machineDate)}">${escapeHtml(entry.date)}</time>
        <span class="entry-location">${escapeHtml(entry.location)}</span>
        <span class="entry-tag">${escapeHtml(entry.type)}</span>
      </aside>
      <div class="entry-body">
        <h3>${escapeHtml(entry.title)}</h3>
        <p class="entry-summary">${escapeHtml(entry.summary)}</p>
        <div class="journal">
          ${entry.journal.map(paragraph => `<p>${escapeHtml(paragraph)}</p>`).join("")}
        </div>
        <div class="consequence">
          <div><strong>Entscheidung</strong>${escapeHtml(entry.decision.choice)}</div>
          <div><strong>Folge</strong>${escapeHtml(entry.decision.consequence)}</div>
        </div>
      </div>
    </article>
  `).join("");

  ledger.innerHTML = entries.map(entry => `
    <article class="decision-item">
      <header>
        <h3>${escapeHtml(entry.decision.title)}</h3>
        <time datetime="${escapeHtml(entry.machineDate)}">${escapeHtml(entry.date)}</time>
      </header>
      <p>${escapeHtml(entry.decision.analysis)}</p>
      <p class="lesson">${escapeHtml(entry.decision.lesson)}</p>
    </article>
  `).join("");
}

function renderProfile(profile) {
  const container = document.querySelector("#profile");
  const skillSummary = Object.entries(profile.skills || {})
    .map(([name, rank]) => `${name}: ${rank}`);
  const progression = profile.progression || [];
  const latestProgression = progression[progression.length - 1];

  const progressionCard = latestProgression ? `
    <article class="fact-card progression-card">
      <p class="progression-kicker">Stufe ${escapeHtml(latestProgression.level)} · ${escapeHtml(latestProgression.context)}</p>
      <h3>${escapeHtml(latestProgression.title)}</h3>
      <div class="progression-grid">
        <div>
          <strong>Fähigkeiten</strong>
          ${renderList(latestProgression.skillChanges)}
        </div>
        <div>
          <strong>Beschwörung</strong>
          <p>${escapeHtml(latestProgression.invocation)}</p>
        </div>
        <div>
          <strong>Talent</strong>
          <p>${escapeHtml(latestProgression.talent)}</p>
        </div>
      </div>
      <p class="progression-meaning">${escapeHtml(latestProgression.meaning)}</p>
    </article>
  ` : "";

  container.innerHTML = `
    <div class="profile-story">
      ${profile.biography.map(paragraph => `<p>${escapeHtml(paragraph)}</p>`).join("")}
      <blockquote>${escapeHtml(profile.motto)}</blockquote>
    </div>
    <div class="profile-facts">
      <article class="fact-card">
        <h3>Herkunft</h3>
        <p>${escapeHtml(profile.origin)}</p>
      </article>
      <article class="fact-card">
        <h3>Identität</h3>
        <p>${escapeHtml(profile.identity)}</p>
      </article>
      <article class="fact-card">
        <h3>Aktueller Stand</h3>
        <p>Stufe ${escapeHtml(profile.level)} · ${escapeHtml(profile.combatRole)}</p>
        ${renderList(skillSummary)}
      </article>
      <article class="fact-card">
        <h3>Überzeugungen</h3>
        ${renderList(profile.beliefs)}
      </article>
      <article class="fact-card">
        <h3>Ziele</h3>
        ${renderList(profile.goals)}
      </article>
      ${progressionCard}
    </div>
  `;
}

async function init() {
  try {
    const [entrySources, profile] = await Promise.all([
      loadJson("./data/entry-sources.json"),
      loadJson("./data/serin.json")
    ]);
    const entryGroups = await Promise.all(entrySources.map(loadJson));
    renderEntries(entryGroups.flat());
    renderProfile(profile);
  } catch (error) {
    console.error(error);
    document.querySelector("#entries").innerHTML = `
      <article class="entry-card loading-card">
        <p>Die Chronik konnte gerade nicht geöffnet werden. Bitte lade die Seite erneut.</p>
      </article>`;
    document.querySelector("#profile").innerHTML = `<p>Serins Profil konnte gerade nicht geladen werden.</p>`;
  }
}

init();
