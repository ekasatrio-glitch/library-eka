// Entry: splash, sidebar nav, view switching, mount chat + projects, history.
import { postJSON, escapeHtml } from "./api.js";
import { makeHistory } from "./history.js";
import { mountSplash } from "./splash.js";
import { mountChat } from "./chat.js";
import { mountProjects } from "./projects.js";
import { mountDraft } from "./draft.js";
import { mountMindmap } from "./mindmap.js";
import { makeMindmapStore } from "./mindmaps.js";

const history = makeHistory(window.localStorage);

mountSplash(document, window.localStorage);

const viewChat = document.getElementById("view-chat");
const viewProjects = document.getElementById("view-projects");
const chatSide = document.getElementById("chat-side");
const projectsSide = document.getElementById("projects-side");
const navChat = document.getElementById("nav-chat");
const navProjects = document.getElementById("nav-projects");
const recentList = document.getElementById("recent-list");

const viewDraft = document.getElementById("view-draft");
const viewMindmap = document.getElementById("view-mindmap");
const navDraft = document.getElementById("nav-draft");
const navMindmap = document.getElementById("nav-mindmap");
const mindmapSide = document.getElementById("mindmap-side");
const mindmapRecent = document.getElementById("mindmap-recent");
const mindmaps = makeMindmapStore(window.localStorage);

const NAVS = [navChat, navProjects, navDraft, navMindmap];
const VIEWS = [viewChat, viewProjects, viewDraft, viewMindmap];
const SIDES = [chatSide, projectsSide, mindmapSide];

function activate(nav, view, sideEl) {
  NAVS.forEach(n => n.classList.toggle("active", n === nav));
  VIEWS.forEach(v => { v.hidden = v !== view; });
  // Show exactly one sidebar body. Draft reuses the Chat body (Recent).
  SIDES.forEach(s => { s.hidden = s !== sideEl; });
}
function showChat() { activate(navChat, viewChat, chatSide); }
function showProjects() { activate(navProjects, viewProjects, projectsSide); }
function showDraft() { activate(navDraft, viewDraft, chatSide); }
function showMindmap() { activate(navMindmap, viewMindmap, mindmapSide); }

navChat.addEventListener("click", showChat);
navProjects.addEventListener("click", showProjects);
navDraft.addEventListener("click", showDraft);
navMindmap.addEventListener("click", showMindmap);

// ----- global chat + localStorage history -----
let currentConvId = null;

function renderRecent() {
  const items = history.list();
  recentList.innerHTML = items.map(c =>
    `<div class="hist${c.id === currentConvId ? " active" : ""}" data-cid="${c.id}">` +
    `<span>${escapeHtml(c.title || "(tanpa judul)")}</span><button class="del" data-del="${c.id}" type="button" title="Hapus">✕</button></div>`
  ).join("") || `<div class="gap" style="padding:6px 11px">Belum ada percakapan.</div>`;
  recentList.querySelectorAll("[data-cid]").forEach(el =>
    el.addEventListener("click", e => {
      if (e.target.matches("[data-del]")) return;
      openConversation(el.dataset.cid);
    }));
  recentList.querySelectorAll("[data-del]").forEach(b =>
    b.addEventListener("click", () => {
      history.remove(b.dataset.del);
      if (currentConvId === b.dataset.del) newChat();
      else renderRecent();
    }));
}

function persist(messages) {
  if (!messages.length) return;
  history.save({
    id: currentConvId,
    title: messages[0].q.slice(0, 48),
    scope: "global",
    messages,
    updatedAt: Date.now(),
  });
  renderRecent();
}

function newChat() {
  currentConvId = "c" + Date.now();
  mountChat(viewChat, {
    showNudge: false,
    endpoint: q => postJSON("/ask", { question: q }),
    onExchange: persist,
  });
  renderRecent();
  showChat();
}

function openConversation(id) {
  const conv = history.get(id);
  if (!conv) return;
  currentConvId = id;
  mountChat(viewChat, {
    showNudge: false,
    initial: conv.messages,
    endpoint: q => postJSON("/ask", { question: q }),
    onExchange: persist,
  });
  renderRecent();
  showChat();
}

document.getElementById("new-conversation").addEventListener("click", newChat);

// ----- projects -----
const projects = mountProjects(viewProjects, document.getElementById("projects-list"), {
  activateProjectsView: showProjects,
});
projects.loadList();
document.getElementById("new-project").addEventListener("click", () => {
  const name = prompt("Nama proyek baru:");
  if (name && name.trim()) projects.createProject(name.trim());
});

// draft + mindmap (stateless, mounted once)
mountDraft(viewDraft);
mountMindmap(viewMindmap, { store: mindmaps, recentEl: mindmapRecent });

// boot
newChat();
