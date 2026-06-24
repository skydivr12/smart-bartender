import threading
import socket
from flask import Flask, jsonify, request, render_template_string

# ─────────────────────────────────────────
#  HTML template — the entire web UI
#  in one self-contained file
# ─────────────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Smart Bartender</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #121212; color: #ecf0f1;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    max-width: 600px; margin: 0 auto; padding: 16px;
  }
  h1 { color: #3498db; margin-bottom: 4px; font-size: 1.6rem; }
  .subtitle { color: #7f8c8d; font-size: 0.85rem; margin-bottom: 24px; }
  h2 { font-size: 1.1rem; color: #bdc3c7; margin: 24px 0 10px;
       border-bottom: 1px solid #2c2c2c; padding-bottom: 6px; }
  .card {
    background: #1e1e1e; border-radius: 10px;
    padding: 14px 16px; margin-bottom: 8px;
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px;
  }
  .card-left { flex: 1; min-width: 0; }
  .card-title { font-weight: 600; font-size: 1rem; margin-bottom: 2px;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card-sub { color: #7f8c8d; font-size: 0.8rem; }
  .badge {
    font-size: 0.7rem; font-weight: 700; padding: 2px 8px;
    border-radius: 99px; white-space: nowrap;
  }
  .badge-low  { background: #7d4e00; color: #f39c12; }
  .badge-ok   { background: #1a3a1a; color: #2ecc71; }
  .badge-empty{ background: #2c2c2c; color: #7f8c8d; }
  select, input[type=number], input[type=text] {
    background: #2a2a2a; color: #ecf0f1;
    border: 1px solid #3a3a3a; border-radius: 6px;
    padding: 6px 10px; font-size: 0.9rem;
  }
  select { max-width: 140px; }
  input[type=number] { width: 80px; }
  input[type=text]   { width: 100%; margin-bottom: 8px; }
  button {
    background: #3498db; color: #fff; border: none;
    border-radius: 8px; padding: 10px 18px;
    font-size: 0.95rem; font-weight: 600; cursor: pointer;
  }
  button:hover   { background: #2980b9; }
  button.danger  { background: #c0392b; }
  button.danger:hover { background: #a93226; }
  button.success { background: #27ae60; }
  button.success:hover { background: #219a52; }
  button.small   { padding: 6px 12px; font-size: 0.8rem; }
  .pour-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .pour-row select { flex: 1; }
  .msg {
    margin: 12px 0; padding: 10px 14px; border-radius: 8px;
    font-size: 0.9rem; display: none;
  }
  .msg.show  { display: block; }
  .msg.ok    { background: #1a3a1a; color: #2ecc71; }
  .msg.error { background: #3a1a1a; color: #e74c3c; }
  .ingredient-row {
    display: flex; align-items: center;
    gap: 8px; margin-bottom: 6px;
  }
  .ingredient-row label { flex: 1; font-size: 0.9rem; color: #bdc3c7; }
  .low-bar {
    height: 4px; border-radius: 2px; margin-top: 4px;
    background: #2c2c2c; overflow: hidden;
  }
  .low-bar-fill { height: 100%; border-radius: 2px; background: #3498db; }
</style>
</head>
<body>

<h1>🍹 Smart Bartender</h1>
<p class="subtitle" id="hostname">Loading...</p>

<div id="msg" class="msg"></div>

<!-- ── POUR ─────────────────────────────── -->
<h2>Pour a Drink</h2>
<div class="card" style="flex-direction:column;align-items:stretch;gap:10px">
  <div class="pour-row">
    <select id="pour-drink"><option>Loading...</option></select>
    <select id="pour-size">
      <option value="Small">Small</option>
      <option value="Regular" selected>Regular</option>
      <option value="Large">Large</option>
    </select>
    <select id="pour-strength">
      <option value="Normal" selected>Normal</option>
      <option value="Double">Double</option>
    </select>
  </div>
  <button class="success" onclick="pourDrink()">Pour Drink</button>
</div>

<!-- ── PUMPS ─────────────────────────────── -->
<h2>Pump Configuration</h2>
<div id="pump-list">Loading...</div>

<!-- ── DRINKS ────────────────────────────── -->
<h2>Drink Menu</h2>
<div id="drink-list">Loading...</div>

<!-- ── ADD DRINK ─────────────────────────── -->
<h2>Add Custom Drink</h2>
<div class="card" style="flex-direction:column;align-items:stretch;gap:8px">
  <input type="text" id="new-drink-name" placeholder="Drink name">
  <div id="new-drink-ingredients">Loading...</div>
  <button onclick="addDrink()">Save Drink</button>
</div>

<br>

<script>
function showMsg(text, ok=true) {
  const el = document.getElementById('msg');
  el.textContent = text;
  el.className = 'msg show ' + (ok ? 'ok' : 'error');
  setTimeout(() => el.className = 'msg', 4000);
}

async function api(path, method='GET', body=null) {
  const opts = { method, headers: {'Content-Type':'application/json'} };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch('/api/' + path, opts);
  return r.json();
}

// ── Load everything on page load ──────────
async function loadAll() {
  document.getElementById('hostname').textContent =
    'http://' + window.location.hostname + ':5000';
  await loadPumps();
  await loadDrinks();
}

// ── Pumps ─────────────────────────────────
async function loadPumps() {
  const data = await api('pumps');
  const el   = document.getElementById('pump-list');
  const opts = await api('options');
  el.innerHTML = '';

  for (const [key, pump] of Object.entries(data)) {
    const pct = pump.volume_ml > 0
      ? Math.min(100, Math.round(pump.volume_ml / 10))
      : 0;
    const badge = pump.value === null
      ? '<span class="badge badge-empty">Empty</span>'
      : pump.is_low
        ? '<span class="badge badge-low">LOW</span>'
        : '<span class="badge badge-ok">OK</span>';

    // build liquid select
    let optHtml = '<option value="">— Empty —</option>';
    for (const o of opts) {
      const sel = o.value === pump.value ? 'selected' : '';
      optHtml += `<option value="${o.value}" ${sel}>${o.name}</option>`;
    }

    el.innerHTML += `
      <div class="card" style="flex-direction:column;align-items:stretch">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span class="card-title">${pump.name}</span>
          ${badge}
        </div>
        <div class="low-bar">
          <div class="low-bar-fill" style="width:${pct}%"></div>
        </div>
        <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
          <select id="liq-${key}" style="flex:1">${optHtml}</select>
          <input type="number" id="vol-${key}" value="${pump.volume_ml}"
                 min="0" max="2000" step="50" placeholder="ml">
          <button class="small" onclick="savePump('${key}')">Save</button>
        </div>
      </div>`;
  }
}

async function savePump(key) {
  const liq = document.getElementById('liq-' + key).value || null;
  const vol = parseInt(document.getElementById('vol-' + key).value) || 0;
  const r   = await api('pumps/' + key, 'POST', {value: liq, volume_ml: vol});
  showMsg(r.message, r.ok);
  loadPumps();
}

// ── Drinks ────────────────────────────────
async function loadDrinks() {
  const drinks = await api('drinks');
  const el     = document.getElementById('drink-list');
  const pour   = document.getElementById('pour-drink');
  const ingEl  = document.getElementById('new-drink-ingredients');
  const pumps  = await api('pumps');

  // populate pour dropdown
  pour.innerHTML = '';
  for (const d of drinks) {
    pour.innerHTML += `<option value="${d.name}">${d.name}</option>`;
  }

  // drink list cards
  el.innerHTML = '';
  for (const d of drinks) {
    const ings = Object.entries(d.ingredients)
      .map(([k,v]) => `${k}: ${v}ml`).join(', ');
    el.innerHTML += `
      <div class="card">
        <div class="card-left">
          <div class="card-title">${d.name}</div>
          <div class="card-sub">${ings}</div>
        </div>
        <button class="small danger" onclick="deleteDrink('${d.name}')">
          Delete
        </button>
      </div>`;
  }

  // ingredient rows for custom drink builder
  ingEl.innerHTML = '';
  for (const [key, pump] of Object.entries(pumps)) {
    if (!pump.value) continue;
    ingEl.innerHTML += `
      <div class="ingredient-row">
        <label>${pump.name} — ${pump.value}</label>
        <input type="number" id="ing-${key}" value="0"
               min="0" max="300" step="5" placeholder="ml">
      </div>`;
  }
}

async function deleteDrink(name) {
  if (!confirm('Delete "' + name + '"?')) return;
  const r = await api('drinks/' + encodeURIComponent(name), 'DELETE');
  showMsg(r.message, r.ok);
  loadDrinks();
}

async function addDrink() {
  const name = document.getElementById('new-drink-name').value.trim();
  if (!name) { showMsg('Enter a drink name.', false); return; }

  const pumps = await api('pumps');
  const ingredients = {};
  for (const key of Object.keys(pumps)) {
    const el  = document.getElementById('ing-' + key);
    if (!el) continue;
    const amt = parseInt(el.value) || 0;
    if (amt > 0 && pumps[key].value) {
      ingredients[pumps[key].value] = amt;
    }
  }
  if (Object.keys(ingredients).length === 0) {
    showMsg('Add at least one ingredient.', false); return;
  }
  const r = await api('drinks', 'POST', {name, ingredients});
  showMsg(r.message, r.ok);
  if (r.ok) {
    document.getElementById('new-drink-name').value = '';
    loadDrinks();
  }
}

async function pourDrink() {
  const name     = document.getElementById('pour-drink').value;
  const size     = document.getElementById('pour-size').value;
  const strength = document.getElementById('pour-strength').value;
  const r = await api('pour', 'POST', {name, size, strength});
  showMsg(r.message, r.ok);
}

loadAll();
</script>
</body>
</html>
"""


def get_ip():
    """Gets the Pi's local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def create_web_app(pump_manager, drink_manager):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(HTML)

    @app.route("/api/pumps")
    def get_pumps():
        result = {}
        for key, pump in pump_manager.pumps.items():
            result[key] = {
                "name":      pump.name,
                "value":     pump.value,
                "volume_ml": pump.volume_ml,
                "is_low":    pump.is_low(),
                "is_empty":  pump.is_empty(),
            }
        return jsonify(result)

    @app.route("/api/pumps/<key>", methods=["POST"])
    def set_pump(key):
        if key not in pump_manager.pumps:
            return jsonify({"ok": False, "message": "Pump not found"})
        data = request.json
        pump = pump_manager.pumps[key]
        pump.value     = data.get("value")
        pump.volume_ml = data.get("volume_ml", 0)
        pump_manager.save()
        return jsonify({"ok": True, "message": f"{pump.name} saved."})

    @app.route("/api/options")
    def get_options():
        from drinks import DRINK_OPTIONS
        return jsonify(DRINK_OPTIONS)

    @app.route("/api/drinks")
    def get_drinks():
        return jsonify(drink_manager.drinks)

    @app.route("/api/drinks", methods=["POST"])
    def add_drink():
        data = request.json
        ok, msg = drink_manager.add_drink(
            data.get("name", ""),
            data.get("ingredients", {})
        )
        return jsonify({"ok": ok, "message": msg})

    @app.route("/api/drinks/<name>", methods=["DELETE"])
    def delete_drink(name):
        ok = drink_manager.delete_drink(name)
        msg = "Drink deleted." if ok else "Drink not found."
        return jsonify({"ok": ok, "message": msg})

    @app.route("/api/pour", methods=["POST"])
    def pour():
        data     = request.json
        name     = data.get("name")
        size     = data.get("size", "Regular")
        strength = data.get("strength", "Normal")

        drink = drink_manager.get_drink_by_name(name)
        if not drink:
            return jsonify({"ok": False, "message": "Drink not found."})

        scaled = drink_manager.scale_ingredients(
            drink["ingredients"], size=size, strength=strength)

        available = pump_manager.get_available_ingredients()
        needed    = set(scaled.keys())
        if not needed.issubset(available):
            missing = needed - available
            return jsonify({
                "ok": False,
                "message": f"Missing ingredients: {', '.join(missing)}"
            })

        pump_manager.make_drink(scaled)
        return jsonify({
            "ok": True,
            "message": f"Pouring {name} ({size}, {strength})..."
        })

    return app


def start_web_server(pump_manager, drink_manager, host="0.0.0.0", port=5000):
    """Starts the web server in a background thread."""
    flask_app = create_web_app(pump_manager, drink_manager)
    ip = get_ip()
    print(f"Web interface available at:")
    print(f"  http://bartender.local:5000")
    print(f"  http://{ip}:5000")

    t = threading.Thread(
        target=lambda: flask_app.run(
            host=host, port=port, debug=False, use_reloader=False),
        daemon=True
    )
    t.start()
    return t
