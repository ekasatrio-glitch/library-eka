// Entry: splash, topbar gear, screen routing (Beranda <-> Ruang Kerja).
import { makeHistory } from "./history.js";
import { makeMindmapStore } from "./mindmaps.js";
import { mountSplash } from "./splash.js";
import { mountBeranda } from "./beranda.js";
import { mountWorkspace } from "./workspace.js";
import { wireAdminGear } from "./admin.js";

const history = makeHistory(window.localStorage);
const mindmaps = makeMindmapStore(window.localStorage);
const screen = document.getElementById("screen");

mountSplash(document, window.localStorage);
wireAdminGear(document.getElementById("admin-gear"));

function showBeranda() {
  mountBeranda(screen, { onOpen: openNaskah });
}
function openNaskah(pid) {
  mountWorkspace(screen, pid, { history, mindmaps, onBack: showBeranda });
}

showBeranda();
