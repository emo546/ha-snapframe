// ── Injektované serverom ──────────────────────────────────────────────────────
var CFG              = window.SNAPFRAME_CFG || {};
var TR               = CFG.tr              || {};
var SLIDESHOW_SECS   = CFG.slideshow_secs  || 30;
var SLEEP_START      = CFG.sleep_start     || "";
var SLEEP_END        = CFG.sleep_end       || "";
var WEATHER_INTERVAL = CFG.weather_interval || 8;
var WEEKDAYS         = CFG.weekdays        || [];
var WEEKDAYS_SHORT   = CFG.weekdays_short  || [];
var MONTHS_LIST      = CFG.months          || [];
var WEEK_ORDINALS    = CFG.week_ordinals   || [];

// ── i18n helpers ──────────────────────────────────────────────────────────────
function tr(k)       { return TR[k] || k; }
function trf(k, arr) {
  var s = TR[k] || k;
  for (var i = 0; i < arr.length; i++) { s = s.replace("{" + i + "}", arr[i]); }
  return s;
}

// ── Naplň preložené texty do DOM ──────────────────────────────────────────────
function applyTranslations() {
  document.getElementById("t-app-title").textContent     = tr("app_title");
  document.getElementById("t-app-subtitle").textContent  = tr("app_subtitle");
  document.getElementById("scan-btn").textContent        = tr("scan_btn");
  document.getElementById("t-order-label").textContent   = tr("order_label");
  document.getElementById("btn-order-date").textContent  = tr("order_date");
  document.getElementById("btn-order-rand").textContent  = tr("order_random");
  document.getElementById("t-upload-toggle").textContent = tr("upload_toggle");
  document.getElementById("t-upload-album-label").textContent = tr("upload_album_label");
  document.getElementById("t-upload-root").textContent   = tr("upload_root");
  document.getElementById("t-upload-new-option").textContent  = tr("upload_new_option");
  document.getElementById("upload-new-album").placeholder     = tr("upload_new_ph");
  document.getElementById("t-upload-files-label").textContent = tr("upload_files_label");
  document.getElementById("upload-file-btn").textContent = tr("upload_select");
  document.getElementById("t-upload-gps-hint").textContent = tr("upload_gps_hint");
  document.getElementById("upload-go-btn").textContent   = tr("upload_go");
  document.getElementById("ss-msg").textContent          = tr("no_photos");
  document.getElementById("conn-lost").textContent      = tr("conn_lost");
  document.getElementById("t-del-title").textContent     = tr("delete_title");
  document.getElementById("t-del-sub").textContent       = tr("delete_sub");
  document.getElementById("t-del-yes").textContent       = tr("delete_yes");
  document.getElementById("t-del-no").textContent        = tr("delete_no");
  document.getElementById("t-settings-title").textContent       = tr("settings_title");
  document.getElementById("t-settings-sleep-label").textContent = tr("settings_sleep_label");
  document.getElementById("t-theme-black").textContent          = tr("theme_black");
  document.getElementById("t-theme-stars").textContent          = tr("theme_stars");
  document.getElementById("t-settings-close").textContent       = tr("settings_close");
  // — kalendár vývozu odpadu —
  document.getElementById("t-waste-open-btn").textContent       = tr("waste_open_btn");
  document.getElementById("t-waste-title").textContent          = tr("waste_title");
  document.getElementById("t-waste-enabled-label").textContent  = tr("waste_enabled_label");
  document.getElementById("waste-en-on").textContent            = tr("waste_on");
  document.getElementById("waste-en-off").textContent           = tr("waste_off");
  document.getElementById("t-waste-display-label").textContent  = tr("waste_display_label");
  document.getElementById("waste-mode-overlay").textContent     = tr("waste_mode_overlay");
  document.getElementById("waste-mode-slide").textContent       = tr("waste_mode_slide");
  document.getElementById("waste-mode-both").textContent        = tr("waste_mode_both");
  document.getElementById("t-waste-interval-label").textContent = tr("waste_interval_label");
  document.getElementById("t-waste-days-label").textContent     = tr("waste_days_label");
  document.getElementById("t-waste-show-on-day").textContent    = tr("waste_show_on_day");
  document.getElementById("t-waste-start-hour").textContent     = tr("waste_start_hour");
  document.getElementById("t-waste-end-hour").textContent       = tr("waste_end_hour");
  document.getElementById("t-waste-rules-label").textContent    = tr("waste_rules_label");
  document.getElementById("t-waste-add-rule").textContent       = tr("waste_add_rule");
  document.getElementById("t-waste-preview").textContent        = tr("waste_preview");
  document.getElementById("t-waste-save").textContent           = tr("waste_save");
  document.getElementById("t-waste-close").textContent          = tr("settings_close");
  document.getElementById("t-waste-type-label").textContent     = tr("waste_type_label");
  document.getElementById("t-waste-name-label").textContent     = tr("waste_name_label");
  document.getElementById("t-waste-recurrence").textContent     = tr("waste_recurrence");
  document.getElementById("waste-kind-weekly").textContent      = tr("waste_kind_weekly");
  document.getElementById("waste-kind-monthly").textContent     = tr("waste_kind_monthly");
  document.getElementById("waste-kind-dates").textContent       = tr("waste_kind_dates");
  document.getElementById("t-waste-weekday").textContent        = tr("waste_weekday");
  document.getElementById("t-waste-weekday-2").textContent      = tr("waste_weekday");
  document.getElementById("t-waste-every-weeks").textContent    = tr("waste_every_weeks");
  document.getElementById("t-waste-anchor").textContent         = tr("waste_anchor");
  document.getElementById("t-waste-anchor-hint").textContent    = tr("waste_anchor_hint");
  document.getElementById("t-waste-monthly-by").textContent     = tr("waste_monthly_by");
  document.getElementById("waste-by-weekday").textContent       = tr("waste_by_weekday");
  document.getElementById("waste-by-day").textContent           = tr("waste_by_day");
  document.getElementById("t-waste-week-of-month").textContent  = tr("waste_week_of_month");
  document.getElementById("t-waste-day-of-month").textContent   = tr("waste_day_of_month");
  document.getElementById("t-waste-months").textContent         = tr("waste_months");
  document.getElementById("t-waste-dates-label").textContent    = tr("waste_dates_label");
  document.getElementById("t-waste-add-date").textContent       = tr("waste_add_date");
  document.getElementById("t-waste-add-skip").textContent       = tr("waste_add_date");
  document.getElementById("t-waste-add-extra").textContent      = tr("waste_add_date");
  document.getElementById("t-waste-valid-from").textContent     = tr("waste_valid_from");
  document.getElementById("t-waste-valid-to").textContent       = tr("waste_valid_to");
  document.getElementById("t-waste-skip-label").textContent     = tr("waste_skip_label");
  document.getElementById("t-waste-extra-label").textContent    = tr("waste_extra_label");
  document.getElementById("t-waste-rule-ok").textContent        = tr("waste_save");
  document.getElementById("t-waste-rule-cancel").textContent    = tr("waste_cancel");
  document.getElementById("t-waste-rule-delete").textContent    = tr("waste_delete");
  // — import harmonogramu —
  document.getElementById("t-wimp-open").textContent   = tr("wimp_open");
  document.getElementById("t-wimp-intro").textContent  = tr("wimp_intro");
  document.getElementById("t-wimp-pick").textContent   = tr("wimp_pick");
  document.getElementById("t-wimp-add").textContent    = tr("wimp_add");
  document.getElementById("t-wimp-cancel").textContent = tr("waste_cancel");
}

// ── Settings (sleep theme) ──────────────────────────────────────────────────
var SLEEP_THEME_KEY = "snapframe_sleep_theme";
var sleepTheme = "black";
try {
  var _saved = localStorage.getItem(SLEEP_THEME_KEY);
  if (_saved === "black" || _saved === "stars") { sleepTheme = _saved; }
} catch (e) {}

function openSettings() {
  document.getElementById("settings-dialog").style.display = "block";
  _refreshThemeUI();
}
function closeSettings() {
  document.getElementById("settings-dialog").style.display = "none";
}
function _refreshThemeUI() {
  document.getElementById("theme-opt-black").className = "theme-opt" + (sleepTheme === "black" ? " active" : "");
  document.getElementById("theme-opt-stars").className = "theme-opt" + (sleepTheme === "stars" ? " active" : "");
}
function chooseSleepTheme(theme) {
  sleepTheme = theme;
  try { localStorage.setItem(SLEEP_THEME_KEY, theme); } catch (e) {}
  _refreshThemeUI();
  var el = document.getElementById("screen-sleep");
  el.className = "theme-" + theme;
  if (theme === "stars" && !_starsBuilt) { buildStarfield(); }
}

// ── Star field ────────────────────────────────────────────────────────────────
var _starsBuilt = false;
var _meteorInterval = null;

function buildStarfield() {
  var svg = document.getElementById("starfield-svg");
  if (!svg) { return; }
  var w = window.innerWidth, h = window.innerHeight;
  svg.setAttribute("viewBox", "0 0 " + w + " " + h);
  var ns = "http://www.w3.org/2000/svg";
  var frag = document.createDocumentFragment();
  var count = Math.round((w * h) / 9000);
  count = Math.max(70, Math.min(180, count));
  for (var i = 0; i < count; i++) {
    var x = Math.random() * w;
    var y = Math.random() * h;
    var sizeRoll = Math.random();
    var r = sizeRoll > 0.94 ? (1.6 + Math.random() * 1.1)
          : sizeRoll > 0.75 ? (1.0 + Math.random() * 0.6)
          : (0.45 + Math.random() * 0.5);
    var circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", x.toFixed(1));
    circle.setAttribute("cy", y.toFixed(1));
    circle.setAttribute("r", r.toFixed(2));
    var willTwinkle = Math.random() < 0.55;
    var cls = "sf-star" + (willTwinkle ? " twinkle" : "");
    circle.setAttribute("class", cls);
    var baseOpacity = 0.35 + Math.random() * 0.5;
    if (willTwinkle) {
      var dur = (2.4 + Math.random() * 3.6).toFixed(2);
      var delay = (-1 * Math.random() * 6).toFixed(2);
      circle.style.webkitAnimationDuration = dur + "s";
      circle.style.animationDuration = dur + "s";
      circle.style.webkitAnimationDelay = delay + "s";
      circle.style.animationDelay = delay + "s";
      circle.style.setProperty("--sf-min", Math.max(0.12, baseOpacity - 0.35).toFixed(2));
      circle.style.setProperty("--sf-max", Math.min(1, baseOpacity + 0.4).toFixed(2));
    } else {
      circle.style.opacity = baseOpacity.toFixed(2);
    }
    frag.appendChild(circle);
  }
  svg.innerHTML = "";
  svg.appendChild(frag);
  _starsBuilt = true;
}

function _spawnMeteor() {
  var host = document.getElementById("screen-sleep");
  if (!host || sleepTheme !== "stars" || !_sleeping) { return; }
  var m = document.createElement("div");
  m.className = "sf-meteor";
  m.style.left = (20 + Math.random() * 55) + "%";
  m.style.top  = (5 + Math.random() * 25) + "%";
  host.appendChild(m);
  setTimeout(function() { if (m.parentNode) { m.parentNode.removeChild(m); } }, 3300);
}

function _startMeteorShowerLoop() {
  if (_meteorInterval) { clearInterval(_meteorInterval); }
  _meteorInterval = setInterval(function() {
    if (Math.random() < 0.55) { _spawnMeteor(); }
  }, 9000);
}
function _stopMeteorShowerLoop() {
  if (_meteorInterval) { clearInterval(_meteorInterval); _meteorInterval = null; }
}

// ── Sleep mode ────────────────────────────────────────────────────────────────
function _toMin(t) {
  var p = t.split(":"); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10);
}
var _sleeping = false;

function _startRefreshTimer() {
  refreshTimer = setInterval(function() {
    fetchPhotos(function(newList) {
      if (!newList.length) { return; }
      photos = newList;
      if (currentIndex >= photos.length) { currentIndex = photos.length - 1; }
    });
  }, 5 * 60 * 1000);
}

function checkSleep() {
  var el = document.getElementById("screen-sleep");
  if (!SLEEP_START || !SLEEP_END) { el.style.display = "none"; return; }
  var now = new Date();
  var cur = now.getHours() * 60 + now.getMinutes();
  var s   = _toMin(SLEEP_START);
  var e   = _toMin(SLEEP_END);
  var sleeping = (s < e) ? (cur >= s && cur < e) : (cur >= s || cur < e);
  if (sleeping === _sleeping) { return; }
  _sleeping = sleeping;
  if (sleeping) {
    el.className = "theme-" + sleepTheme;
    el.style.display = "block";
    if (sleepTheme === "stars") {
      if (!_starsBuilt) { buildStarfield(); }
      _startMeteorShowerLoop();
    }
    if (advanceTimer) { clearInterval(advanceTimer); advanceTimer = null; }
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
    updateWasteBadge();
    maybeDailyReload();
  } else {
    el.style.display = "none";
    _stopMeteorShowerLoop();
    if (slideshowActive && photos.length > 0) {
      startAdvanceTimer();
      _startRefreshTimer();
    }
    // po prebudení je už možno „zajtra“ – prepočítaj pripomienku
    fetchWasteStatus();
  }
}
setInterval(checkSleep, 60000);

// ── Adresovanie ───────────────────────────────────────────────────────────────
// Stránka môže bežať na koreni (tablet ide priamo na port) alebo pod cestou
// Home Assistant ingressu. Všetky requesty sú preto relatívne k stránke.
var API_BASE = (function() {
  var path = location.pathname || "/";
  return path.charAt(path.length - 1) === "/" ? path : path.replace(/[^\/]*$/, "");
})();

function api(path) {
  return API_BASE + String(path).replace(/^\//, "");
}

// Šírka, akú má zmysel pýtať pre fotku na celú obrazovku. Bez toho dostane
// Retina iPad 1024 px roztiahnutých cez 2048 fyzických – a vyzerá to tak.
function displayWidth() {
  var dpr  = window.devicePixelRatio || 1;
  var side = Math.max(screen.width || 0, screen.height || 0,
                      window.innerWidth || 0, window.innerHeight || 0);
  return Math.min(2048, Math.round(side * dpr)) || 1024;
}

// ── API token ─────────────────────────────────────────────────────────────────
// Ak je add-on nakonfigurovaný s api_token, zápisové endpointy ho vyžadujú.
// Čítanie ostáva otvorené, takže rám sa rozbehne aj bez neho – token si appka
// vypýta až keď sa niečo naozaj mení (upload, mazanie, uloženie kalendára).
var TOKEN_KEY = "snapframe_api_token";

function apiToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
}
function setApiToken(t) {
  try { localStorage.setItem(TOKEN_KEY, t || ""); } catch (e) {}
}
function withToken(xhr) {
  var t = apiToken();
  if (t) { xhr.setRequestHeader("X-SnapFrame-Token", t); }
}
/** Vráti true, ak požiadavka zlyhala na tokene – vtedy si ho vypýta a zopakuje ju. */
function tokenRetry(xhr, retry) {
  if (xhr.status !== 401) { return false; }
  var t = window.prompt(tr("token_prompt"), apiToken());
  if (t !== null && t !== "") { setApiToken(t.replace(/^\s+|\s+$/g, "")); retry(); }
  return true;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
// Rám visí na stene mesiace a add-on sa občas reštartuje (update HA, výpadok
// NAS). Bez opakovania by jediná neúspešná odpoveď nechala obrazovku zamrznutú
// až do ručného obnovenia stránky.
var OFFLINE_RETRIES = [2000, 5000, 15000, 30000];
var _offline = false;

function setOffline(state) {
  if (state === _offline) { return; }
  _offline = state;
  var el = document.getElementById("conn-lost");
  if (el) { el.style.display = state ? "block" : "none"; }
}

function xhrGet(url, cb, _attempt) {
  var attempt = _attempt || 0;
  var xhr = new XMLHttpRequest();
  xhr.open("GET", api(url), true);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    if (xhr.status === 200) {
      setOffline(false);
      cb(null, xhr.responseText);
      return;
    }
    // 4xx je odpoveď servera, nie výpadok – opakuje sa len spojenie a 5xx.
    if ((xhr.status === 0 || xhr.status >= 500) && attempt < OFFLINE_RETRIES.length) {
      setOffline(true);
      setTimeout(function() { xhrGet(url, cb, attempt + 1); }, OFFLINE_RETRIES[attempt]);
      return;
    }
    if (xhr.status === 0) { setOffline(true); }
    cb(new Error("HTTP " + xhr.status), xhr.responseText);
  };
  try {
    xhr.send();
  } catch (e) {
    setOffline(true);
    if (attempt < OFFLINE_RETRIES.length) {
      setTimeout(function() { xhrGet(url, cb, attempt + 1); }, OFFLINE_RETRIES[attempt]);
    } else {
      cb(e, "");
    }
  }
}
function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function encodePath(p) {
  var parts = p.split("/"), out = [];
  for (var i = 0; i < parts.length; i++) { out.push(encodeURIComponent(parts[i])); }
  return out.join("/");
}

// ── Scan trigger ──────────────────────────────────────────────────────────────
function triggerScan() {
  var btn = document.getElementById("scan-btn");
  var xhr = new XMLHttpRequest();
  xhr.open("POST", api("/scan"), true);
  withToken(xhr);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    if (tokenRetry(xhr, triggerScan)) { return; }
    btn.textContent = tr("scan_started");
    btn.className = "scan-btn done";
    setTimeout(function() {
      btn.textContent = tr("scan_btn");
      btn.className = "scan-btn";
    }, 3000);
  };
  xhr.send();
}

// ── Výberná obrazovka ─────────────────────────────────────────────────────────
var currentOrder = "date";
var albumNames   = [];

function setOrder(order) {
  currentOrder = order;
  document.getElementById("btn-order-date").className = (order === "date") ? "order-btn active" : "order-btn";
  document.getElementById("btn-order-rand").className = (order === "random") ? "order-btn active" : "order-btn";
}

function loadAlbums() {
  var listEl = document.getElementById("album-list");
  listEl.innerHTML = "<div class='sel-empty'>" + escHtml(tr("loading_albums")) + "</div>";
  xhrGet("/albums", function(err, text) {
    if (err) {
      listEl.innerHTML = "<div class='sel-empty'>" + escHtml(err.message) + "</div>";
      return;
    }
    var data;
    try { data = JSON.parse(text); } catch(e) { return; }
    var albums = data.albums || [];
    albumNames = [];
    for (var i = 0; i < albums.length; i++) { albumNames.push(albums[i].name); }
    var totalCount = 0;
    for (var i = 0; i < albums.length; i++) { totalCount += (albums[i].count || 0); }
    var html = "<button class='album-btn all-btn' onclick='startSlideshow(\"all\")'>"
             + "<div class='album-btn-overlay'></div><div class='album-btn-inner'>"
             + "<span class='album-icon all-icon'>&#9654;</span>"
             + escHtml(tr("all_photos"))
             + "<span class='album-count'>" + totalCount + "</span>"
             + "</div></button>";
    for (var i = 0; i < albums.length; i++) {
      html += "<button class='album-btn' id='album-btn-" + i + "' onclick='startSlideshowIdx(" + i + ")'>"
            + "<div class='album-btn-overlay'></div><div class='album-btn-inner'>"
            + "<span class='album-icon'>&#128193;</span>"
            + escHtml(albums[i].name)
            + "<span class='album-count'>" + (albums[i].count || 0) + "</span>"
            + "</div></button>";
    }
    if (albums.length === 0) {
      html += "<div class='sel-empty'>" + escHtml(tr("no_albums")) + "</div>";
    }
    listEl.innerHTML = html;
    loadAlbumCovers();
    populateUploadAlbums(albums);
  });
}

function loadAlbumCovers() {
  for (var i = 0; i < albumNames.length; i++) {
    (function(name, idx) {
      var btn = document.getElementById("album-btn-" + idx);
      if (!btn) { return; }
      var img = new Image();
      var coverUrl = api("/album-cover/" + encodeURIComponent(name));
      img.onload = function() {
        btn.style.backgroundImage = "url('" + coverUrl + "')";
      };
      img.src = coverUrl;
    })(albumNames[i], i);
  }
}

function startSlideshowIdx(i) { startSlideshow(albumNames[i]); }

function goBack() {
  _showToken++;                      // zahoď rozrobené načítanie fotky
  if (advanceTimer) { clearInterval(advanceTimer); advanceTimer = null; }
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  photos = []; currentIndex = -1; activeIsA = true;
  var a = document.getElementById("photoA");
  var b = document.getElementById("photoB");
  a.style.backgroundImage = ""; a.className = "photo";
  b.style.backgroundImage = ""; b.className = "photo";
  document.getElementById("overlay-date").innerHTML     = "";
  document.getElementById("overlay-location").innerHTML = "";
  document.getElementById("photo-counter").innerHTML    = "";
  hideWeatherSlide();
  hideWasteSlide();
  document.getElementById("waste-badge").className = "";
  photosSinceWeather = 0;
  photosSinceWaste   = 0;
  slideshowActive = false;
  document.getElementById("screen-slideshow").style.display = "none";
  document.getElementById("screen-select").style.display    = "";
  loadAlbums();
}

// ── Slideshow ─────────────────────────────────────────────────────────────────
var photos = [], currentIndex = -1, activeIsA = true;
var advanceTimer = null, refreshTimer = null, slideshowActive = false;
var currentAlbum = "";
var EFFECTS = ["fade", "zoomin", "zoomout", "slideleft", "slideup"];

function startSlideshow(album) {
  currentAlbum = album; slideshowActive = true;
  document.getElementById("screen-select").style.display    = "none";
  document.getElementById("screen-slideshow").style.display = "block";
  document.getElementById("ss-msg").style.display           = "none";
  fetchPhotosAndStart();
  _startRefreshTimer();
}

function fetchPhotos(cb) {
  xhrGet("/photos?album=" + encodeURIComponent(currentAlbum) + "&order=" + currentOrder,
    function(err, text) {
      if (err) { if (cb) { cb([]); } return; }
      try { if (cb) { cb(JSON.parse(text).photos || []); } }
      catch(e) { if (cb) { cb([]); } }
    });
}

function fetchPhotosAndStart() {
  fetchPhotos(function(list) {
    photos = list;
    if (!photos.length) {
      document.getElementById("ss-msg").style.display = "block"; return;
    }
    currentIndex = 0; activeIsA = true;
    showPhoto(0); startAdvanceTimer();
  });
}

function pickEffect() { return EFFECTS[Math.floor(Math.random() * EFFECTS.length)]; }

function photoUrl(filename) {
  return api("/thumb/" + encodePath(filename)) + "?w=" + displayWidth();
}

/** Načíta fotku do cache prehliadača a zavolá cb, keď je naozaj pripravená. */
function preloadPhoto(filename, cb) {
  var img = new Image();
  var done = false;
  function finish(ok) {
    if (done) { return; }
    done = true;
    if (cb) { cb(ok); }
  }
  img.onload  = function() { finish(true); };
  img.onerror = function() { finish(false); };
  // Poistka pre pomalý share: prechod nesmie čakať donekonečna.
  setTimeout(function() { finish(false); }, 8000);
  img.src = photoUrl(filename);
  return img;
}

var _nextPreload = null;

function showPhoto(index) {
  if (!photos.length) { return; }
  hideWeatherSlide();
  hideWasteSlide();
  var idx      = ((index % photos.length) + photos.length) % photos.length;
  var filename = photos[idx];
  var nextEl   = activeIsA ? document.getElementById("photoB") : document.getElementById("photoA");
  var prevEl   = activeIsA ? document.getElementById("photoA") : document.getElementById("photoB");
  var effect   = pickEffect();
  var mine     = ++_showToken;

  // Prechod sa spustí až keď je fotka stiahnutá – inak sa na pomalej sieti
  // odfadeuje prázdny rám a fotka doskočí až doprostred animácie.
  preloadPhoto(filename, function() {
    if (mine !== _showToken) { return; }     // medzitým sa prepli inde
    nextEl.style.backgroundImage = "url(" + photoUrl(filename) + ")";
    nextEl.className = "photo " + effect + "-start";
    setTimeout(function() {
      if (mine !== _showToken) { return; }
      nextEl.className = "photo visible " + effect + "-end";
      prevEl.className = "photo";
    }, 50);
    activeIsA = !activeIsA;
    // Nasledujúca fotka sa ťahá počas toho, ako sa pozerá na túto.
    if (photos.length > 1) {
      _nextPreload = preloadPhoto(photos[(idx + 1) % photos.length], null);
    }
  });

  document.getElementById("photo-counter").innerHTML = (idx + 1) + " / " + photos.length;
  loadExifOverlay(filename);
  updateWasteBadge();
}
var _showToken = 0;

function loadExifOverlay(filename) {
  document.getElementById("overlay-date").innerHTML     = "";
  document.getElementById("overlay-location").innerHTML = "";
  xhrGet("/exif/" + encodePath(filename), function(err, text) {
    if (err) { return; }
    try {
      var data = JSON.parse(text);
      document.getElementById("overlay-date").innerHTML     = escHtml(data.date     || "");
      document.getElementById("overlay-location").innerHTML = escHtml(data.location || "");
    } catch(e) {}
  });
}

// Rám beží mesiace bez obnovenia stránky. Starému Safari po čase rastie pamäť
// a nový build add-onu by sa inak neprejavil, kým stránku niekto ručne
// neobnoví – raz za deň sa teda obnoví sama (v noci, ak je nočný režim).
var _pageLoadedAt = Date.now();
var PAGE_MAX_AGE  = 24 * 3600 * 1000;

function maybeDailyReload() {
  if (Date.now() - _pageLoadedAt < PAGE_MAX_AGE) { return false; }
  if (SLEEP_START && SLEEP_END && !_sleeping) { return false; }   // počkaj na noc
  location.reload();
  return true;
}

function advanceTick() {
  if (maybeDailyReload()) { return; }
  if (weatherModeActive && weatherData && photosSinceWeather >= WEATHER_INTERVAL) {
    photosSinceWeather = 0;
    photosSinceWaste++;
    showWeatherSlide();
    return;
  }
  if (wasteModeHas("slide") && currentWasteAlert() &&
      photosSinceWaste >= (wasteCfg.photo_interval || 10)) {
    photosSinceWaste = 0;
    photosSinceWeather++;
    showWasteSlide();
    return;
  }
  photosSinceWeather++;
  photosSinceWaste++;
  currentIndex = (currentIndex + 1) % photos.length;
  showPhoto(currentIndex);
}

function startAdvanceTimer() {
  if (advanceTimer) { clearInterval(advanceTimer); }
  advanceTimer = setInterval(advanceTick, SLIDESHOW_SECS * 1000);
}

// ── Weather mode ──────────────────────────────────────────────────────────────
var weatherModeActive   = false;
var weatherData         = null;
var photosSinceWeather  = 0;

var WEATHER_EMOJI = {
  "sunny": "☀️", "clear-night": "🌙",
  "partlycloudy": "⛅", "cloudy": "☁️",
  "fog": "🌫️", "windy": "🌬️", "windy-variant": "🌬️",
  "rainy": "🌧️", "pouring": "🌧️",
  "lightning": "⛈️", "lightning-rainy": "⛈️",
  "hail": "🧊", "snowy": "❄️", "snowy-rainy": "🌨️",
  "exceptional": "⚠️"
};

function fetchWeatherStatus() {
  xhrGet("/weather", function(err, text) {
    if (err) { return; }
    try {
      var data = JSON.parse(text);
      weatherModeActive = !!data.active;
      weatherData = data.data || null;
    } catch (e) {}
  });
}
setInterval(fetchWeatherStatus, 60000);

// Po otočení obrazovky (portrét <-> landscape) prekresli weather slide,
// aby sa počet a rozloženie hodinových kariet prispôsobili orientácii.
function _weatherIsVisible() {
  return document.getElementById("weather-slide").className.indexOf("visible") !== -1;
}
window.addEventListener("resize", function() {
  if (_weatherIsVisible() && weatherData) { showWeatherSlide(); }
});

function showWeatherSlide() {
  var d = weatherData;
  if (!d) { return; }
  document.getElementById("weather-icon").textContent = WEATHER_EMOJI[d.condition] || "🌡️";
  document.getElementById("weather-temp").textContent = (d.temperature != null) ? Math.round(d.temperature) + "°" : "--°";
  document.getElementById("weather-cond").textContent = d.condition_label || "";
  var parts = [];
  if (d.forecast_high != null) {
    parts.push(escHtml(tr("weather_high")) + " <span class=\"val\">" + Math.round(d.forecast_high) + "°</span>");
  }
  if (d.forecast_low != null) {
    parts.push(escHtml(tr("weather_low")) + " <span class=\"val\">" + Math.round(d.forecast_low) + "°</span>");
  }
  document.getElementById("weather-range").innerHTML = parts.join("");
  renderHourly(d.hourly);
  document.getElementById("weather-date").textContent = new Date().toLocaleDateString();
  document.getElementById("overlay-date").innerHTML     = "";
  document.getElementById("overlay-location").innerHTML = "";
  document.getElementById("photo-counter").innerHTML    = "";
  document.getElementById("waste-badge").className      = "";
  document.getElementById("weather-slide").className = "visible";
}

/** HH:MM v lokálnej zóne tabletu. iso prichádza z HA v UTC – kontajner
 * add-onu nemá spoľahlivú lokálnu zónu, prehliadač na tablete áno (rovnaký
 * princíp ako pri kalendári odpadu). Padá späť na h.time (spočítané na
 * serveri), keď iso chýba alebo ho prehliadač nevie rozparsovať. */
function _hourLocalTime(h) {
  if (h.iso) {
    var d = new Date(h.iso);
    if (!isNaN(d.getTime())) {
      var hh = d.getHours();
      var mm = d.getMinutes();
      return (hh < 10 ? "0" : "") + hh + ":" + (mm < 10 ? "0" : "") + mm;
    }
  }
  return h.time || "";
}

function renderHourly(hourly) {
  var host = document.getElementById("weather-hourly");
  if (!hourly || !hourly.length) { host.innerHTML = ""; host.style.display = "none"; return; }
  host.style.display = "";
  // Portrét (na výšku): hodiny sú riadky zhora dole. Landscape (na stene):
  // 6 veľkých kariet vedľa seba. 6 položiek sa zmestí aj na telefón na výšku
  // a ostáva všade veľké a čitateľné zďaleka. Rozloženie rieši CSS podľa orientácie.
  var maxItems = 6;
  var list = hourly;
  if (list.length > maxItems) {
    // Rovnomerne navzorkuj naprieč celým rozsahom vrátane prvej a poslednej hodiny.
    var sampled = [];
    for (var k = 0; k < maxItems; k++) {
      sampled.push(list[Math.round(k * (list.length - 1) / (maxItems - 1))]);
    }
    list = sampled;
  }
  var html = "";
  for (var j = 0; j < list.length; j++) {
    var h = list[j];
    var ico  = WEATHER_EMOJI[h.condition] || "🌡️";
    var temp = (h.temperature != null) ? Math.round(h.temperature) + "°" : "--";
    html += "<div class=\"weather-hour" + (j === 0 ? " now" : "") + "\">"
          + "<div class=\"wh-time\">" + escHtml(_hourLocalTime(h)) + "</div>"
          + "<div class=\"wh-ico\">" + ico + "</div>"
          + "<div class=\"wh-temp\">" + escHtml(temp) + "</div>"
          + "</div>";
  }
  host.innerHTML = html;
}

function hideWeatherSlide() {
  document.getElementById("weather-slide").className = "";
}

// ── Kalendár vývozu odpadu: beh na fotorámiku ─────────────────────────────────
var wasteCfg          = null;   // nastavenia zo /waste/status
var wasteByDate       = {};     // "YYYY-MM-DD" -> [{id,label,icon,color}, ...]
var wasteUpcoming     = [];     // surový zoznam pre náhľad v editore
var photosSinceWaste  = 0;
var wasteSlideVisible = false;

function _pad2(n) { return (n < 10 ? "0" : "") + n; }

// Lokálny ISO dátum (NIE toISOString – ten prepočíta na UTC a v CEST posunie deň).
function _isoLocal(d) {
  return d.getFullYear() + "-" + _pad2(d.getMonth() + 1) + "-" + _pad2(d.getDate());
}

function fetchWasteStatus() {
  xhrGet("/waste/status", function(err, text) {
    if (err) { return; }
    try {
      var data = JSON.parse(text);
      wasteCfg      = data;
      wasteUpcoming = data.upcoming || [];
      wasteByDate   = {};
      for (var i = 0; i < wasteUpcoming.length; i++) {
        wasteByDate[wasteUpcoming[i].date] = wasteUpcoming[i].types || [];
      }
    } catch (e) { return; }
    updateWasteBadge();
  });
}
setInterval(fetchWasteStatus, 15 * 60 * 1000);

// Ktorý najbližší termín (v rámci nastaveného predstihu) máme práve pripomínať.
// „Dnešok“ určuje prehliadač na tablete – ten má správnu lokálnu časovú zónu.
function currentWasteAlert() {
  if (!wasteCfg || !wasteCfg.enabled) { return null; }
  var now   = new Date();
  var start = wasteCfg.show_on_day ? 0 : 1;
  for (var off = start; off <= wasteCfg.days_before; off++) {
    var d     = new Date(now.getFullYear(), now.getMonth(), now.getDate() + off);
    var types = wasteByDate[_isoLocal(d)];
    if (!types || !types.length) { continue; }
    // deň-vopred pripomienku netlačiť skôr, než si používateľ praje
    if (off >= 1 && now.getHours() < (wasteCfg.start_hour || 0)) { continue; }
    // v deň vývozu pripomienku po nastavenej hodine už neukazovať (kontajner je vonku zbytočne dlho)
    if (off === 0 && now.getHours() >= (wasteCfg.end_hour == null ? 24 : wasteCfg.end_hour)) { continue; }
    return { days: off, date: _isoLocal(d), types: types };
  }
  return null;
}

function wasteModeHas(what) {
  if (!wasteCfg) { return false; }
  return wasteCfg.mode === what || wasteCfg.mode === "both";
}

function wasteWhenLabel(days) {
  if (days === 0) { return tr("waste_today"); }
  if (days === 1) { return tr("waste_tomorrow"); }
  if (days <= 4)  { return trf("waste_in_days_few",  [days]); }
  return trf("waste_in_days_many", [days]);
}

function wasteIcons(types) {
  var out = "";
  for (var i = 0; i < types.length; i++) { out += types[i].icon; }
  return out;
}

function wasteNames(types) {
  var out = [];
  for (var i = 0; i < types.length; i++) { out.push(types[i].label); }
  return out;
}

function _wasteFormatDate(iso) {
  var p = iso.split("-");
  var d = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
  return WEEKDAYS[(d.getDay() + 6) % 7] + " · " + d.toLocaleDateString();
}

function updateWasteBadge() {
  var el = document.getElementById("waste-badge");
  if (!el) { return; }
  var a = currentWasteAlert();
  if (!a || !wasteModeHas("overlay") || !slideshowActive ||
      wasteSlideVisible || _weatherIsVisible() || _sleeping) {
    el.className = ""; return;
  }
  document.getElementById("waste-badge-ico").innerHTML  = escHtml(wasteIcons(a.types));
  document.getElementById("waste-badge-when").innerHTML = escHtml(wasteWhenLabel(a.days));
  document.getElementById("waste-badge-what").innerHTML = escHtml(wasteNames(a.types).join(" · "));
  el.style.borderLeftColor = a.types[0].color || "#9aa5b1";
  el.className = "visible";
}

function showWasteSlide() {
  var a = currentWasteAlert();
  if (!a) { return; }
  var names = wasteNames(a.types), html = "";
  for (var i = 0; i < names.length; i++) {
    if (i) { html += "<span class=\"wn-sep\"> · </span>"; }
    html += escHtml(names[i]);
  }
  document.getElementById("waste-slide-icons").innerHTML = escHtml(wasteIcons(a.types));
  document.getElementById("waste-slide-when").innerHTML  =
      escHtml(wasteWhenLabel(a.days) + " · " + tr("waste_headline"));
  document.getElementById("waste-slide-names").innerHTML = html;
  document.getElementById("waste-slide-accent").style.background = a.types[0].color || "#7cb342";
  document.getElementById("waste-slide-hint").innerHTML  =
      escHtml(a.days === 0 ? tr("waste_hint_today") : tr("waste_hint"));
  document.getElementById("waste-slide-date").innerHTML  = escHtml(_wasteFormatDate(a.date));
  document.getElementById("overlay-date").innerHTML     = "";
  document.getElementById("overlay-location").innerHTML = "";
  document.getElementById("photo-counter").innerHTML    = "";
  document.getElementById("waste-badge").className      = "";
  document.getElementById("waste-slide").className      = "visible";
  wasteSlideVisible = true;
}

function hideWasteSlide() {
  document.getElementById("waste-slide").className = "";
  wasteSlideVisible = false;
}

// ── Kalendár vývozu odpadu: editor ───────────────────────────────────────────
var wdCfg      = null;   // pracovná kópia celého configu
var wdTypes    = [];     // katalóg druhov odpadu zo servera
var wdMaxRules = 40;
var wdRule     = null;   // pracovná kópia práve editovaného pravidla
var wdRuleIdx  = -1;     // index v wdCfg.rules, -1 = nové pravidlo

function openWasteDialog() {
  closeSettings();
  document.getElementById("waste-dialog").style.display = "block";
  document.getElementById("waste-main").style.display   = "block";
  document.getElementById("waste-editor").style.display = "none";
  document.getElementById("waste-import").style.display = "none";
  document.getElementById("waste-dialog").scrollTop     = 0;
  wdStatus("", "");
  xhrGet("/waste/config", function(err, text) {
    if (err) { wdStatus(tr("waste_save_err"), "err"); return; }
    try {
      var data   = JSON.parse(text);
      wdCfg      = data.config || {};
      wdTypes    = data.types  || [];
      wdMaxRules = data.max_rules || 40;
    } catch (e) { wdStatus(tr("waste_save_err"), "err"); return; }
    if (!wdCfg.rules) { wdCfg.rules = []; }
    wdRenderMain();
  });
}

function closeWasteDialog() {
  document.getElementById("waste-dialog").style.display = "none";
  fetchWasteStatus();
}

function wdStatus(msg, cls) {
  var el = document.getElementById("waste-status");
  el.innerHTML = escHtml(msg || "");
  el.className = "wd-status" + (cls ? " " + cls : "");
}

function _seg(id, active) {
  var el = document.getElementById(id);
  if (el) { el.className = "wd-opt" + (active ? " active" : ""); }
}

function wdSetEnabled(on) { wdCfg.enabled = !!on; wdRenderMain(); }
function wdSetMode(m)     { wdCfg.mode = m;      wdRenderMain(); }

function wdStep(key, delta, lo, hi) {
  var v = (parseInt(wdCfg[key], 10) || 0) + delta;
  if (v < lo) { v = lo; }
  if (v > hi) { v = hi; }
  wdCfg[key] = v;
  if (key === "days_before" && v === 0) { wdCfg.show_on_day = true; }
  wdRenderMain();
}

function wdToggleShowOnDay() {
  if (wdCfg.days_before === 0) { return; }   // inak by sa nezobrazilo nikdy nič
  wdCfg.show_on_day = !wdCfg.show_on_day;
  wdRenderMain();
}

function wdRenderMain() {
  _seg("waste-en-on",  wdCfg.enabled);
  _seg("waste-en-off", !wdCfg.enabled);
  _seg("waste-mode-overlay", wdCfg.mode === "overlay");
  _seg("waste-mode-slide",   wdCfg.mode === "slide");
  _seg("waste-mode-both",    wdCfg.mode === "both");
  document.getElementById("waste-interval-group").style.display =
      (wdCfg.mode === "overlay") ? "none" : "";
  document.getElementById("waste-interval-val").innerHTML = wdCfg.photo_interval;
  document.getElementById("waste-days-val").innerHTML     = wdCfg.days_before;
  document.getElementById("waste-hour-val").innerHTML     = _pad2(wdCfg.start_hour) + ":00";
  document.getElementById("waste-end-hour-val").innerHTML =
      wdCfg.end_hour >= 24 ? tr("waste_end_hour_all_day") : (_pad2(wdCfg.end_hour) + ":00");
  document.getElementById("waste-showday-check").className =
      "wd-check" + (wdCfg.show_on_day ? " on" : "");
  wdRenderRules();
  wdRenderPreview();
}

function wdTypeInfo(id) {
  for (var i = 0; i < wdTypes.length; i++) {
    if (wdTypes[i].id === id) { return wdTypes[i]; }
  }
  return { id: id, label: id, icon: "♻️", color: "#9aa5b1" };
}

// Slovenčina skloňuje 1 / 2–4 / 5+ inak; ostatné jazyky použijú rovnaký tvar.
function wdCountLabel(n) {
  if (n === 1)              { return trf("waste_dates_one",  [n]); }
  if (n >= 2 && n <= 4)     { return trf("waste_dates_few",  [n]); }
  return trf("waste_dates_many", [n]);
}

function wdRuleSummary(rule) {
  var rec = rule.recurrence || {}, out = "";
  if (rec.kind === "weekly") {
    var n = rec.interval_weeks || 1;
    out = WEEKDAYS[rec.weekday || 0] + " · " +
          (n === 1 ? tr("waste_every_week") : trf("waste_every_n_weeks", [n]));
  } else if (rec.kind === "monthly") {
    if (rec.monthly_by === "day") {
      out = tr("waste_day_of_month") + ": " + (rec.day_of_month || 1) + ".";
    } else {
      out = WEEK_ORDINALS["" + (rec.week_of_month || 1)] + " " +
            WEEKDAYS[rec.weekday || 0].toLowerCase();
    }
    if (rec.months && rec.months.length) {
      var mm = [];
      for (var i = 0; i < rec.months.length; i++) { mm.push(MONTHS_LIST[rec.months[i] - 1].substr(0, 3)); }
      out += " (" + mm.join(", ") + ")";
    }
  } else {
    out = wdCountLabel((rec.dates || []).length);
  }
  if ((rule.extra || []).length) { out += " +" + rule.extra.length; }
  if ((rule.skip  || []).length) { out += " −" + rule.skip.length; }
  return out;
}

function wdRenderRules() {
  var host = document.getElementById("waste-rule-list");
  var rules = wdCfg.rules || [];
  if (!rules.length) {
    host.innerHTML = "<div class=\"wd-empty\">" + escHtml(tr("waste_no_rules")) + "</div>";
  } else {
    var html = "";
    for (var i = 0; i < rules.length; i++) {
      var info = wdTypeInfo(rules[i].type);
      var name = rules[i].label || info.label;
      html += "<div class=\"wd-rule\" style=\"border-left-color:" + escHtml(info.color) + "\""
            + " onclick=\"wdEditRule(" + i + ")\">"
            + "<div class=\"wr-ico\">" + escHtml(info.icon) + "</div>"
            + "<div class=\"wr-txt\"><div class=\"wr-name\">" + escHtml(name) + "</div>"
            + "<div class=\"wr-sub\">" + escHtml(wdRuleSummary(rules[i])) + "</div></div>"
            + "<div class=\"wr-go\">&#8250;</div></div>";
    }
    host.innerHTML = html;
  }
  var addBtn = document.getElementById("t-waste-add-rule");
  addBtn.style.display = (rules.length >= wdMaxRules) ? "none" : "";
}

// Náhľad ukazuje ULOŽENÝ harmonogram (rozvinutý serverom), nie rozpracované zmeny.
function wdRenderPreview() {
  var host = document.getElementById("waste-preview-list");
  if (!wasteUpcoming.length) {
    host.innerHTML = "<div class=\"wd-empty\">" + escHtml(tr("waste_preview_none")) + "</div>";
    return;
  }
  var todayIso = _isoLocal(new Date()), html = "", shown = 0;
  for (var i = 0; i < wasteUpcoming.length && shown < 6; i++) {
    if (wasteUpcoming[i].date < todayIso) { continue; }
    shown++;
    html += "<div class=\"wd-preview-day\"><div class=\"wp-date\">"
          + escHtml(_wasteFormatDate(wasteUpcoming[i].date)) + "</div>"
          + "<div class=\"wp-types\">"
          + escHtml(wasteIcons(wasteUpcoming[i].types) + " " +
                    wasteNames(wasteUpcoming[i].types).join(", "))
          + "</div></div>";
  }
  host.innerHTML = shown ? html
      : "<div class=\"wd-empty\">" + escHtml(tr("waste_preview_none")) + "</div>";
}

function wdSaveConfig() {
  wdStatus("…", "");
  var xhr = new XMLHttpRequest();
  xhr.open("POST", api("/waste/config"), true);
  xhr.setRequestHeader("Content-Type", "application/json");
  withToken(xhr);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    if (tokenRetry(xhr, wdSaveConfig)) { return; }
    if (xhr.status !== 200) { wdStatus(tr("waste_save_err"), "err"); return; }
    try {
      var data = JSON.parse(xhr.responseText);
      if (data.config) { wdCfg = data.config; if (!wdCfg.rules) { wdCfg.rules = []; } }
    } catch (e) {}
    wdStatus(tr("waste_saved"), "ok");
    // po uložení si vypýtaj rozvinutý harmonogram, nech sedí náhľad aj rámik
    xhrGet("/waste/status", function(err2, text2) {
      if (!err2) {
        try {
          var st = JSON.parse(text2);
          wasteCfg      = st;
          wasteUpcoming = st.upcoming || [];
          wasteByDate   = {};
          for (var i = 0; i < wasteUpcoming.length; i++) {
            wasteByDate[wasteUpcoming[i].date] = wasteUpcoming[i].types || [];
          }
        } catch (e2) {}
      }
      updateWasteBadge();
      wdRenderMain();
    });
  };
  xhr.send(JSON.stringify(wdCfg));
}

// ── Import harmonogramu ──────────────────────────────────────────────────────
var wimpSeries = [];   // rady rozpoznané zo súboru
var wimpYear   = 0;

function wimpOpen() {
  document.getElementById("waste-main").style.display   = "none";
  document.getElementById("waste-import").style.display = "block";
  document.getElementById("waste-dialog").scrollTop     = 0;
  wimpReset();
}

function wimpClose() {
  document.getElementById("waste-import").style.display = "none";
  document.getElementById("waste-main").style.display   = "block";
  document.getElementById("waste-dialog").scrollTop     = 0;
  wimpReset();
  wdRenderMain();
}

function wimpReset() {
  wimpSeries = []; wimpYear = 0;
  document.getElementById("wimp-result").innerHTML = "";
  document.getElementById("waste-import-file").value = "";
  document.getElementById("t-wimp-add").style.display = "none";
  wimpStatus("", "");
}

function wimpStatus(msg, cls) {
  var el = document.getElementById("wimp-status");
  el.innerHTML = escHtml(msg || "");
  el.className = "wd-status" + (cls ? " " + cls : "");
}

function wimpErrKey(code) {
  if (code === "too_large")           { return "wimp_err_large"; }
  if (code === "unsupported_format")  { return "wimp_err_format"; }
  if (code === "no_api_key")          { return "wimp_err_novision"; }
  if (code === "no_calendar_found" || code === "no_marks_found" ||
      code === "pdf_parse_failed"     || code === "not_pdf") { return "wimp_err_parse"; }
  return "wimp_err_generic";
}

function wimpUpload(input) {
  if (!input.files || !input.files.length) { return; }
  wimpStatus(tr("wimp_working"), "");
  document.getElementById("wimp-result").innerHTML = "";
  document.getElementById("t-wimp-add").style.display = "none";
  var fd = new FormData();
  fd.append("file", input.files[0]);
  var xhr = new XMLHttpRequest();
  xhr.open("POST", api("/waste/import"), true);
  withToken(xhr);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    if (tokenRetry(xhr, function() { wimpUpload(input); })) { return; }
    var data = null;
    try { data = JSON.parse(xhr.responseText); } catch (e) {}
    if (!data || !data.ok) {
      var code = data ? data.error : "";
      // Ak parser neuspel a vision nie je k dispozícii, povedz to konkrétne.
      if (data && data.vision_available === false && code !== "too_large") {
        code = "no_api_key";
      }
      wimpStatus(tr(wimpErrKey(code)), "err");
      return;
    }
    wimpSeries = data.series || [];
    wimpYear   = data.year || 0;
    for (var i = 0; i < wimpSeries.length; i++) {
      wimpSeries[i].selected = false;
      wimpSeries[i].type = wimpSeries[i].suggested_type || "other";
    }
    wimpStatus(tr(data.source === "vision" ? "wimp_via_vision" : "wimp_via_pdf"), "ok");
    wimpRender();
  };
  xhr.send(fd);
}

function wimpRender() {
  var host = document.getElementById("wimp-result");
  if (!wimpSeries.length) { host.innerHTML = ""; return; }
  var html = "<div class=\"wd-label\">"
           + escHtml(trf("wimp_found", [wimpSeries.length, wimpYear])) + "</div>"
           + "<div class=\"wimp-hint\">" + escHtml(tr("wimp_hint")) + "</div>";
  for (var i = 0; i < wimpSeries.length; i++) {
    var s = wimpSeries[i];
    var sw = "background:" + escHtml(s.fill)
           + (s.outline ? ";border-color:" + escHtml(s.outline) : "");
    var sub = [];
    if (s.summary) { sub.push(s.summary); }
    sub.push(s.count + "\u00d7");
    if (s.dates && s.dates.length) { sub.push(s.dates[0] + " \u2026 " + s.dates[s.dates.length - 1]); }
    html += "<div class=\"wimp-serie" + (s.selected ? " on" : "") + "\" onclick=\"wimpToggle(" + i + ")\">"
          + "<div class=\"ws-sw\"><div class=\"ws-chip\" style=\"" + sw + "\"></div></div>"
          + "<div class=\"ws-txt\"><div class=\"ws-name\">"
          + escHtml(s.colour_name || s.fill) + "</div>"
          + "<div class=\"ws-sub\">" + escHtml(sub.join(" \u00b7 ")) + "</div></div>"
          + "<div class=\"ws-box\">" + (s.selected ? "\u2713" : "\u25cb") + "</div></div>";
    if (s.selected) {
      html += "<select class=\"wimp-type\" onchange=\"wimpSetType(" + i + ",this.value)\">";
      for (var j = 0; j < wdTypes.length; j++) {
        html += "<option value=\"" + escHtml(wdTypes[j].id) + "\""
              + (wdTypes[j].id === s.type ? " selected" : "") + ">"
              + escHtml(wdTypes[j].icon + " " + wdTypes[j].label) + "</option>";
      }
      html += "</select>";
    }
  }
  host.innerHTML = html;
  var any = false;
  for (var k = 0; k < wimpSeries.length; k++) { if (wimpSeries[k].selected) { any = true; } }
  document.getElementById("t-wimp-add").style.display = any ? "" : "none";
}

function wimpToggle(i)      { wimpSeries[i].selected = !wimpSeries[i].selected; wimpRender(); }
function wimpSetType(i, v)  { wimpSeries[i].type = v; }

function wimpAdd() {
  var added = 0;
  for (var i = 0; i < wimpSeries.length; i++) {
    var s = wimpSeries[i];
    if (!s.selected || !s.dates || !s.dates.length) { continue; }
    wdCfg.rules.push({
      id: _newRuleId(), type: s.type, label: "",
      recurrence: { kind: "dates", dates: s.dates.slice(0) },
      from: "", to: "", skip: [], extra: []
    });
    added++;
  }
  if (!added) { wimpStatus(tr("wimp_none_selected"), "err"); return; }
  // Import sám osebe nemá zmysel, kým je pripomienka vypnutá.
  wdCfg.enabled = true;
  wimpClose();
  wdStatus(trf("wimp_added", [added]), "ok");
}

// ── Editor jedného zvozu ─────────────────────────────────────────────────────
function _newRuleId() {
  return "r" + Date.now().toString(36) + Math.floor(Math.random() * 1000).toString(36);
}

function wdNewRule() {
  wdRuleIdx = -1;
  wdRule = {
    id: _newRuleId(), type: (wdTypes[0] ? wdTypes[0].id : "mixed"), label: "",
    recurrence: { kind: "weekly", weekday: 0, interval_weeks: 1, anchor: "", months: [] },
    from: "", to: "", skip: [], extra: []
  };
  wdOpenEditor();
}

function wdEditRule(idx) {
  wdRuleIdx = idx;
  var src = wdCfg.rules[idx];
  var rec = src.recurrence || {};
  wdRule = {
    id: src.id || _newRuleId(), type: src.type, label: src.label || "",
    recurrence: {
      kind:           rec.kind || "weekly",
      weekday:        rec.weekday || 0,
      interval_weeks: rec.interval_weeks || 1,
      anchor:         rec.anchor || "",
      week_of_month:  rec.week_of_month || 1,
      day_of_month:   rec.day_of_month || 1,
      monthly_by:     rec.monthly_by || "weekday",
      months:         (rec.months || []).slice(0),
      dates:          (rec.dates  || []).slice(0)
    },
    from: src.from || "", to: src.to || "",
    skip: (src.skip || []).slice(0), extra: (src.extra || []).slice(0)
  };
  wdOpenEditor();
}

function wdOpenEditor() {
  document.getElementById("waste-main").style.display   = "none";
  document.getElementById("waste-editor").style.display = "block";
  document.getElementById("waste-dialog").scrollTop     = 0;
  document.getElementById("t-waste-rule-delete").style.display = (wdRuleIdx < 0) ? "none" : "";
  document.getElementById("waste-name-input").value  = wdRule.label || "";
  document.getElementById("waste-from-input").value  = wdRule.from  || "";
  document.getElementById("waste-to-input").value    = wdRule.to    || "";
  document.getElementById("waste-anchor-input").value = wdRule.recurrence.anchor || "";
  wdBuildTypeSeg();
  wdBuildWeekdaySegs();
  wdBuildWomSelect();
  wdBuildMonthChips();
  wdRenderEditor();
}

function wdBuildTypeSeg() {
  var host = document.getElementById("waste-type-seg"), html = "";
  for (var i = 0; i < wdTypes.length; i++) {
    var t = wdTypes[i];
    html += "<div class=\"wd-opt\" id=\"wd-type-" + escHtml(t.id) + "\""
          + " onclick=\"wdSetType('" + escHtml(t.id) + "')\">"
          + "<div style=\"font-size:24px;line-height:1.2\">" + escHtml(t.icon) + "</div>"
          + "<div style=\"font-size:11px;margin-top:3px\">" + escHtml(t.label) + "</div></div>";
  }
  host.innerHTML = html;
}

function wdBuildWeekdaySegs() {
  var html = "";
  for (var i = 0; i < 7; i++) {
    html += "<div class=\"wd-opt\" id=\"__PFX__" + i + "\" onclick=\"wdSetWeekday(" + i + ")\">"
          + escHtml(WEEKDAYS_SHORT[i]) + "</div>";
  }
  document.getElementById("waste-weekday-seg").innerHTML  = html.replace(/__PFX__/g, "wd-wd-");
  document.getElementById("waste-weekday-seg2").innerHTML = html.replace(/__PFX__/g, "wd-wd2-");
}

function wdBuildWomSelect() {
  var sel = document.getElementById("waste-wom-select"), html = "";
  var order = ["1", "2", "3", "4", "5", "-1"];
  for (var i = 0; i < order.length; i++) {
    html += "<option value=\"" + order[i] + "\">" + escHtml(WEEK_ORDINALS[order[i]]) + "</option>";
  }
  sel.innerHTML = html;
}

function wdBuildMonthChips() {
  var host = document.getElementById("waste-months-chips"), html = "";
  for (var m = 1; m <= 12; m++) {
    html += "<div class=\"wd-chip month\" id=\"wd-month-" + m + "\" onclick=\"wdToggleMonth(" + m + ")\">"
          + escHtml(MONTHS_LIST[m - 1].substr(0, 3)) + "</div>";
  }
  host.innerHTML = html;
}

function wdSetType(id)  { wdRule.type = id; wdRenderEditor(); }
function wdSetKind(k)   { wdRule.recurrence.kind = k; wdRenderEditor(); }
function wdSetWeekday(i){ wdRule.recurrence.weekday = i; wdRenderEditor(); }
function wdSetMonthlyBy(v) { wdRule.recurrence.monthly_by = v; wdRenderEditor(); }
function wdReadWom()    { wdRule.recurrence.week_of_month = parseInt(document.getElementById("waste-wom-select").value, 10); }
function wdReadAnchor() { wdRule.recurrence.anchor = _wdCleanDate(document.getElementById("waste-anchor-input").value); }
function wdReadRange()  {
  wdRule.from = _wdCleanDate(document.getElementById("waste-from-input").value);
  wdRule.to   = _wdCleanDate(document.getElementById("waste-to-input").value);
}

function wdStepRule(key, delta, lo, hi) {
  var v = (parseInt(wdRule.recurrence[key], 10) || 0) + delta;
  if (v < lo) { v = lo; }
  if (v > hi) { v = hi; }
  wdRule.recurrence[key] = v;
  wdRenderEditor();
}

function wdToggleMonth(m) {
  var arr = wdRule.recurrence.months || [], idx = -1;
  for (var i = 0; i < arr.length; i++) { if (arr[i] === m) { idx = i; break; } }
  if (idx >= 0) { arr.splice(idx, 1); } else { arr.push(m); arr.sort(function(a, b) { return a - b; }); }
  wdRule.recurrence.months = arr;
  wdRenderEditor();
}

function _wdCleanDate(v) {
  v = (v || "").replace(/^\s+|\s+$/g, "");
  return /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : "";
}

function _wdListFor(which) {
  return (which === "dates") ? (wdRule.recurrence.dates = wdRule.recurrence.dates || [])
       : (which === "skip")  ? (wdRule.skip  = wdRule.skip  || [])
                             : (wdRule.extra = wdRule.extra || []);
}

function wdAddDate(which) {
  var input = document.getElementById("waste-" + (which === "dates" ? "date" : which) + "-input");
  var v = _wdCleanDate(input.value);
  if (!v) { return; }
  var list = _wdListFor(which);
  for (var i = 0; i < list.length; i++) { if (list[i] === v) { input.value = ""; return; } }
  list.push(v);
  list.sort();
  input.value = "";
  wdRenderEditor();
}

function wdRemoveDate(which, iso) {
  var list = _wdListFor(which);
  for (var i = 0; i < list.length; i++) {
    if (list[i] === iso) { list.splice(i, 1); break; }
  }
  wdRenderEditor();
}

function _wdRenderChips(hostId, which, list) {
  var host = document.getElementById(hostId), html = "";
  for (var i = 0; i < list.length; i++) {
    html += "<div class=\"wd-chip\" onclick=\"wdRemoveDate('" + which + "','" + escHtml(list[i]) + "')\">"
          + escHtml(list[i]) + "<span class=\"wc-x\">&times;</span></div>";
  }
  host.innerHTML = html;
}

function wdRenderEditor() {
  var rec = wdRule.recurrence;
  for (var i = 0; i < wdTypes.length; i++) {
    _seg("wd-type-" + wdTypes[i].id, wdTypes[i].id === wdRule.type);
  }
  _seg("waste-kind-weekly",  rec.kind === "weekly");
  _seg("waste-kind-monthly", rec.kind === "monthly");
  _seg("waste-kind-dates",   rec.kind === "dates");
  document.getElementById("waste-weekly-box").style.display  = (rec.kind === "weekly")  ? "" : "none";
  document.getElementById("waste-monthly-box").style.display = (rec.kind === "monthly") ? "" : "none";
  document.getElementById("waste-dates-box").style.display   = (rec.kind === "dates")   ? "" : "none";

  for (var w = 0; w < 7; w++) {
    _seg("wd-wd-"  + w, w === rec.weekday);
    _seg("wd-wd2-" + w, w === rec.weekday);
  }
  document.getElementById("waste-weeks-val").innerHTML = rec.interval_weeks || 1;
  document.getElementById("waste-anchor-group").style.display = ((rec.interval_weeks || 1) > 1) ? "" : "none";

  _seg("waste-by-weekday", rec.monthly_by !== "day");
  _seg("waste-by-day",     rec.monthly_by === "day");
  document.getElementById("waste-by-weekday-box").style.display = (rec.monthly_by === "day") ? "none" : "";
  document.getElementById("waste-by-day-box").style.display     = (rec.monthly_by === "day") ? "" : "none";
  document.getElementById("waste-wom-select").value = "" + (rec.week_of_month || 1);
  document.getElementById("waste-dom-val").innerHTML = rec.day_of_month || 1;

  var months = rec.months || [];
  for (var m = 1; m <= 12; m++) {
    var on = false;
    for (var k = 0; k < months.length; k++) { if (months[k] === m) { on = true; break; } }
    var chip = document.getElementById("wd-month-" + m);
    if (chip) { chip.className = "wd-chip month" + (on ? " on" : ""); }
  }

  _wdRenderChips("waste-dates-chips", "dates", rec.dates || []);
  _wdRenderChips("waste-skip-chips",  "skip",  wdRule.skip  || []);
  _wdRenderChips("waste-extra-chips", "extra", wdRule.extra || []);
}

function wdCommitRule() {
  var rec = wdRule.recurrence;
  wdRule.label = document.getElementById("waste-name-input").value.replace(/^\s+|\s+$/g, "");
  wdReadRange();
  if (rec.kind === "weekly") {
    wdReadAnchor();
    // bez referenčného dátumu sa fáza „každý N-tý týždeň“ nedá určiť
    if ((rec.interval_weeks || 1) > 1 && !rec.anchor) {
      document.getElementById("waste-anchor-input").focus();
      return;
    }
  } else if (rec.kind === "dates") {
    if (!(rec.dates || []).length && !(wdRule.extra || []).length) {
      document.getElementById("waste-date-input").focus();
      return;
    }
  }
  if (wdRuleIdx < 0) { wdCfg.rules.push(wdRule); }
  else               { wdCfg.rules[wdRuleIdx] = wdRule; }
  wdCloseEditor();
}

function wdCancelRule() { wdCloseEditor(); }

function wdDeleteRule() {
  if (wdRuleIdx >= 0) { wdCfg.rules.splice(wdRuleIdx, 1); }
  wdCloseEditor();
}

function wdCloseEditor() {
  wdRule = null; wdRuleIdx = -1;
  document.getElementById("waste-editor").style.display = "none";
  document.getElementById("waste-main").style.display   = "block";
  document.getElementById("waste-dialog").scrollTop     = 0;
  wdStatus("", "");
  wdRenderMain();
}

// ── Swipe + dlhý tap ──────────────────────────────────────────────────────────
var swipeTouchStartX = 0, swipeTouchStartY = 0;
var longPressTimer = null, longPressFired = false;

document.addEventListener("touchstart", function(e) {
  swipeTouchStartX = e.touches[0].clientX;
  swipeTouchStartY = e.touches[0].clientY;
  longPressFired = false;
  if (slideshowActive) {
    longPressTimer = setTimeout(function() {
      longPressFired = true; showDeleteDialog();
    }, 750);
  }
}, false);

document.addEventListener("touchmove", function(e) {
  if (!longPressTimer) { return; }
  if (Math.abs(e.touches[0].clientX - swipeTouchStartX) > 10 ||
      Math.abs(e.touches[0].clientY - swipeTouchStartY) > 10) {
    clearTimeout(longPressTimer); longPressTimer = null;
  }
}, false);

document.addEventListener("touchend", function(e) {
  if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
  if (longPressFired || !slideshowActive) { return; }
  var dx = e.changedTouches[0].clientX - swipeTouchStartX;
  var dy = e.changedTouches[0].clientY - swipeTouchStartY;
  if (Math.abs(dy) > 80 && Math.abs(dx) < 80) { goBack(); return; }
  if (dx > 80 && Math.abs(dy) < 60) {
    if (advanceTimer) { clearInterval(advanceTimer); }
    currentIndex = ((currentIndex - 1) + photos.length) % photos.length;
    showPhoto(currentIndex); startAdvanceTimer(); return;
  }
  if (dx < -80 && Math.abs(dy) < 60) {
    if (advanceTimer) { clearInterval(advanceTimer); }
    currentIndex = (currentIndex + 1) % photos.length;
    showPhoto(currentIndex); startAdvanceTimer();
  }
}, false);

// ── Mazanie ───────────────────────────────────────────────────────────────────
function showDeleteDialog()  { document.getElementById("delete-dialog").style.display = "block"; }
function hideDeleteDialog()  { document.getElementById("delete-dialog").style.display = "none"; }

function confirmDelete() {
  hideDeleteDialog();
  if (!photos.length) { return; }
  var filename = photos[currentIndex];
  var xhr = new XMLHttpRequest();
  xhr.open("POST", api("/delete/" + encodePath(filename)), true);
  withToken(xhr);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    if (tokenRetry(xhr, confirmDelete)) { return; }
    if (xhr.status !== 200) { return; }
    photos.splice(currentIndex, 1);
    if (!photos.length) {
      document.getElementById("photoA").className = "photo";
      document.getElementById("photoB").className = "photo";
      document.getElementById("photo-counter").innerHTML = "";
      document.getElementById("ss-msg").style.display = "block"; return;
    }
    currentIndex = currentIndex % photos.length;
    document.getElementById("photoA").className = "photo";
    document.getElementById("photoB").className = "photo";
    activeIsA = true; showPhoto(currentIndex);
  };
  xhr.send();
}

// ── Upload ────────────────────────────────────────────────────────────────────
function toggleUpload() {
  var sec = document.getElementById("upload-section");
  sec.style.display = (sec.style.display === "none" || !sec.style.display) ? "block" : "none";
}

function populateUploadAlbums(albums) {
  var sel = document.getElementById("upload-album");
  while (sel.options.length > 2) { sel.remove(1); }
  for (var i = 0; i < albums.length; i++) {
    var opt = document.createElement("option");
    opt.value = albums[i].name; opt.textContent = albums[i].name;
    sel.insertBefore(opt, sel.options[sel.options.length - 1]);
  }
}

function onAlbumChange(sel) {
  var newInput = document.getElementById("upload-new-album");
  if (sel.value === "__new__") {
    newInput.style.display = "block"; newInput.focus();
  } else {
    newInput.style.display = "none"; newInput.value = "";
  }
}

function onNewAlbumInput(input) {
  var v = "", s = input.value;
  for (var i = 0; i < s.length; i++) {
    var c = s[i];
    if (c !== "/" && c !== "\\") { v += c; }
  }
  input.value = v;
}

function _getTargetAlbum() {
  var sel = document.getElementById("upload-album");
  if (sel.value === "__new__") {
    return document.getElementById("upload-new-album").value.trim();
  }
  return sel.value;
}

function onFilesSelected(input) {
  var btn = document.getElementById("upload-file-btn");
  if (input.files && input.files.length > 0) {
    btn.className = "upload-file-btn has-files";
    btn.textContent = trf("upload_selected", [input.files.length]);
  } else {
    btn.className = "upload-file-btn";
    btn.textContent = tr("upload_select");
  }
  document.getElementById("upload-status").innerHTML = "";
  document.getElementById("upload-status").className = "upload-status";
}

function startUpload() {
  var input  = document.getElementById("upload-files");
  var status = document.getElementById("upload-status");
  if (!input.files || !input.files.length) {
    status.innerHTML = tr("upload_err_files"); status.className = "upload-status err"; return;
  }
  var album = _getTargetAlbum();
  if (document.getElementById("upload-album").value === "__new__" && !album) {
    status.innerHTML = tr("upload_err_name"); status.className = "upload-status err"; return;
  }
  document.getElementById("upload-go-btn").disabled = true;
  _uploadNext(input.files, 0, album, 0);
}

function _uploadNext(files, idx, album, errCount) {
  var status = document.getElementById("upload-status");
  if (idx >= files.length) {
    var msg = trf("upload_done", [files.length]);
    if (errCount > 0) { msg += " " + trf("upload_errors", [errCount]); }
    status.innerHTML = msg;
    status.className = "upload-status " + (errCount > 0 ? "err" : "ok");
    document.getElementById("upload-go-btn").disabled = false;
    document.getElementById("upload-files").value = "";
    document.getElementById("upload-file-btn").className   = "upload-file-btn";
    document.getElementById("upload-file-btn").textContent = tr("upload_select");
    loadAlbums(); return;
  }
  status.className = "upload-status";
  status.innerHTML = trf("upload_progress", [idx + 1, files.length, escHtml(files[idx].name)]);
  var fd = new FormData();
  fd.append("file", files[idx]); fd.append("album", album);
  var xhr = new XMLHttpRequest();
  xhr.open("POST", api("/upload"), true);
  withToken(xhr);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    if (tokenRetry(xhr, function() { _uploadNext(files, idx, album, errCount); })) { return; }
    _uploadNext(files, idx + 1, album, errCount + (xhr.status === 200 ? 0 : 1));
  };
  xhr.send(fd);
}

// ── Štart ─────────────────────────────────────────────────────────────────────
applyTranslations();
checkSleep();
loadAlbums();
fetchWeatherStatus();
fetchWasteStatus();
