// Run with: node --test tests/test_slideshow.js
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(path.join(__dirname,
  "../snapframe/rootfs/usr/share/snapframe/static/app.js"), "utf8");

function frame(userAgent = "") {
  const elements = {}, images = [], timers = new Map(), requests = [];
  let timerId = 0, now = 0;
  const context = vm.createContext({
    window: { SNAPFRAME_CFG: {}, addEventListener() {} },
    location: { pathname: "/" }, screen: {}, navigator: { userAgent },
    document: {
      addEventListener() {},
      getElementById(id) {
        return elements[id] ||= { style: {}, className: "", innerHTML: "" };
      }
    },
    Image: function() { images.push(this); },
    setTimeout(fn, delay) { timers.set(++timerId, { fn, at: now + delay }); return timerId; },
    clearTimeout(id) { timers.delete(id); },
    setInterval() {}, clearInterval() {}
  });
  // Skip startup requests; exercise the actual slideshow and preload functions.
  vm.runInContext(source.slice(0, source.lastIndexOf("\napplyTranslations();")), context);
  context.hideWeatherSlide = context.hideWasteSlide = context.updateBadges = function() {};
  context.loadAlbums = function() {};
  context.xhrGet = function(url, cb) { requests.push({ url, cb }); };
  context.photos = ["old.jpg", "Dovolenka (2024)/fotka (1).jpg", "next.jpg"];
  context.slideshowActive = true;
  context.currentIndex = 0;
  context.displayedPhoto = "old.jpg";
  const el = id => context.document.getElementById(id);
  el("photoA").className = "photo visible fade-end";
  el("photoA").style.backgroundImage = 'url("old.jpg")';
  el("overlay-location").innerHTML = "Old location";
  el("photo-counter").innerHTML = "1 / 3";
  function tick(ms) {
    const until = now + ms;
    while (true) {
      const next = [...timers].filter(([, t]) => t.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) { break; }
      timers.delete(next[0]); now = next[1].at; next[1].fn();
    }
    now = until;
  }
  return { context, el, images, requests, timers, tick };
}

for (const failure of ["network error", "timeout"]) {
  test(`${failure} keeps the last photo, counter and location`, () => {
    const f = frame();
    f.context.showPhoto(1);
    if (failure === "timeout") { f.tick(8000); }
    else { f.images[0].onerror(); }
    f.tick(50);
    assert.match(f.el("photoA").className, /visible/);
    assert.doesNotMatch(f.el("photoB").className, /visible/);
    assert.equal(f.el("overlay-location").innerHTML, "Old location");
    assert.equal(f.el("photo-counter").innerHTML, "1 / 3");
    assert.equal(f.context.activeIsA, true);
  });
}

test("successful load quotes parentheses in CSS URLs and updates metadata at the transition", () => {
  const f = frame();
  f.context.showPhoto(1);
  assert.equal(f.requests.length, 0);
  f.images[0].onload();
  f.tick(50);
  assert.equal(f.el("photoB").style.backgroundImage,
    'url("/thumb/Dovolenka%20(2024)/fotka%20(1).jpg?w=1024")');
  assert.match(f.el("photoB").className, /visible/);
  assert.equal(f.el("photo-counter").innerHTML, "2 / 3");
  assert.equal(f.requests.length, 1);
});

test("rapid navigation during a transition still replaces the visible layer", () => {
  const f = frame();
  f.context.showPhoto(1);
  f.images[0].onload();
  f.context.showPhoto(2); // before the first transition's 50 ms timer
  f.images[f.images.length - 1].onload();
  f.tick(50);
  assert.match(f.el("photoB").className, /visible/);
  assert.doesNotMatch(f.el("photoA").className, /visible/);
  assert.match(f.el("photoB").style.backgroundImage, /next\.jpg/);
});

test("a slow EXIF response cannot overwrite a newer photo's location", () => {
  const f = frame();
  f.context.showPhoto(1); f.images[0].onload(); f.tick(50);
  const oldExif = f.requests[0];
  f.context.showPhoto(2); f.images[f.images.length - 1].onload(); f.tick(50);
  f.requests[1].cb(null, '{"location":"New location"}');
  oldExif.cb(null, '{"location":"Stale location"}');
  assert.equal(f.el("overlay-location").innerHTML, "New location");
});

test("returning to albums cancels an outstanding photo transition", () => {
  const f = frame();
  f.context.showPhoto(1);
  const loaded = f.images[0].onload;
  f.context.goBack(); loaded(); f.tick(50);
  assert.equal(f.el("photoA").className, "photo");
  assert.equal(f.el("photoB").className, "photo");
  assert.equal(f.el("photo-counter").innerHTML, "");
});

test("completed preloads clear their timeout and event handlers", () => {
  const f = frame();
  const results = [];
  const img = f.context.preloadPhoto("old.jpg", ok => results.push(ok));
  const lateError = img.onerror;
  img.onload(); lateError(); f.tick(8000);
  assert.deepEqual(results, [true]);
  assert.equal(f.timers.size, 0);
  assert.equal(img.onload, null);
  assert.equal(img.onerror, null);
});

test("old iPad Safari uses fade and at most a 1024 px preview", () => {
  const f = frame("Mozilla/5.0 (iPad; CPU OS 5_1_1 like Mac OS X) AppleWebKit/534.46 Mobile/9B206 Safari/7534.48.3");
  f.context.screen.width = 2048;
  f.context.window.devicePixelRatio = 2;
  assert.equal(f.context.pickEffect(), "fade");
  assert.equal(f.context.displayWidth(), 1024);
});

test("newer devices retain every original transition and Retina previews", () => {
  const agents = [
    "Mozilla/5.0 (iPad; CPU OS 10_3_4 like Mac OS X) AppleWebKit/603.3.8 Safari/602.1",
    "Mozilla/5.0 (iPad; CPU OS 17_6 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
  ];
  const effects = ["fade", "zoomin", "zoomout", "slideleft", "slideup"];
  for (const agent of agents) {
    const f = frame(agent);
    f.context.screen.width = 1024;
    f.context.window.devicePixelRatio = 2;
    assert.equal(f.context.displayWidth(), 2048);
    effects.forEach((effect, i) => {
      vm.runInContext("Math.random = function() { return " + ((i + 0.5) / effects.length) + "; };", f.context);
      assert.equal(f.context.pickEffect(), effect);
    });
  }
});

test("hidden photo layers release their image after the fade", () => {
  const f = frame();
  f.context.showPhoto(1); f.images[0].onload(); f.tick(1850);
  assert.equal(f.el("photoA").style.backgroundImage, "");
  assert.match(f.el("photoB").style.backgroundImage, /fotka/);
});

test("deletion after a failed load targets the photo still visible", () => {
  const f = frame();
  let xhr;
  f.context.XMLHttpRequest = function() {
    xhr = this;
    this.open = (method, url) => { this.url = url; };
    this.send = function() {};
  };
  f.context.withToken = function() {};
  f.context.tokenRetry = function() { return false; };
  f.context.currentIndex = 1;
  f.context.showPhoto(1); f.images[0].onerror();
  f.context.confirmDelete();
  assert.equal(xhr.url, "/delete/old.jpg");
  xhr.readyState = 4; xhr.status = 200; xhr.onreadystatechange();
  assert.equal(f.context.photos.includes("old.jpg"), false);
  assert.equal(f.context.photos.includes("Dovolenka (2024)/fotka (1).jpg"), true);
});
