import os
import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# ==========================================
# ENVIRONMENT CONFIGURATION
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://hanifsalman11.github.io/obd2-repair-index").rstrip("/")
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3").strip()
CUSTOM_DTC = os.environ.get("CUSTOM_DTC", "").strip()
PAGES_PER_RUN = int(os.environ.get("PAGES_PER_RUN", "3"))

DOCS_DIR = "docs"
DATA_DIR = "data"
PUBLISHED_FILE = os.path.join(DATA_DIR, "published_codes.json")
MONETIZATION_FILE = os.path.join(DATA_DIR, "monetization.json")

SEED_DTCS = [
    "P0420 Catalyst System Efficiency Below Threshold Bank 1",
    "P0171 System Too Lean Bank 1",
    "P0300 Random or Multiple Cylinder Misfire Detected",
    "P0455 Evaporative Emission System Leak Detected Gross Leak",
    "P0128 Coolant Thermostat Below Thermostat Regulating Temperature",
    "P0401 Exhaust Gas Recirculation Flow Insufficient Detected",
    "P0113 Intake Air Temperature Sensor 1 Circuit High",
    "P0101 Mass or Volume Air Flow A Circuit Range Performance",
    "P0135 O2 Sensor Heater Circuit Bank 1 Sensor 1",
    "P0340 Camshaft Position Sensor A Circuit Bank 1",
    "P0442 Evaporative Emission System Leak Detected Small Leak",
    "P0507 Idle Air Control System RPM Higher Than Expected",
    "P0700 Transmission Control System Malfunction",
    "P0174 System Too Lean Bank 2",
    "P0301 Cylinder 1 Misfire Detected",
    "P0302 Cylinder 2 Misfire Detected",
    "P0303 Cylinder 3 Misfire Detected",
    "P0304 Cylinder 4 Misfire Detected",
    "P0440 Evaporative Emission System",
    "P0446 Evaporative Emission System Vent Control Circuit",
    "P0141 O2 Sensor Heater Circuit Bank 1 Sensor 2",
    "P0325 Knock Sensor 1 Circuit Bank 1",
    "P0335 Crankshaft Position Sensor A Circuit",
    "P0011 A Camshaft Position Timing Over-Advanced Bank 1",
    "P0016 Crankshaft Position Camshaft Position Correlation Bank 1 Sensor A",
    "P0191 Fuel Rail Pressure Sensor A Circuit Range Performance",
    "P0299 Turbocharger Supercharger A Underboost Condition",
    "P2096 Post Catalyst Fuel Trim System Too Lean Bank 1",
    "P2138 Throttle Pedal Position Sensor Switch D E Voltage Correlation",
    "U0100 Lost Communication With ECM PCM A",
    "P0102 Mass or Volume Air Flow Circuit Low Input",
    "P0118 Engine Coolant Temperature Sensor 1 Circuit High",
    "P0122 Throttle Pedal Position Sensor Switch A Circuit Low",
    "P0138 O2 Sensor Circuit High Voltage Bank 1 Sensor 2",
    "P0172 System Too Rich Bank 1",
    "P0305 Cylinder 5 Misfire Detected",
    "P0306 Cylinder 6 Misfire Detected",
    "P0430 Catalyst System Efficiency Below Threshold Bank 2",
    "P0456 Evaporative Emission System Leak Detected Very Small Leak",
    "P0500 Vehicle Speed Sensor A",
    "P0505 Idle Control System",
    "P0606 ECM PCM Processor",
    "P0741 Torque Converter Clutch Circuit Performance or Stuck Off",
    "P1135 Air Fuel Ratio Sensor Heater Circuit Response",
    "P2101 Throttle Actuator Control Motor Circuit Range Performance",
    "P2195 O2 Sensor Signal Biased Stuck Lean Bank 1 Sensor 1",
    "P2270 O2 Sensor Signal Biased Stuck Lean Bank 1 Sensor 2",
    "C0035 Left Front Wheel Speed Sensor Supply",
    "B1000 Electronic Control Unit Malfunction",
    "U0121 Lost Communication With Anti-Lock Brake System Control Module"
]


def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Could not parse {filepath}: {e}")
    return default


def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    return re.sub(r"[\s-]+", "-", text).strip("-")


def build_amazon_url(search_keywords, mon_cfg):
    domain = mon_cfg.get("marketplace_domain", "www.amazon.com")
    tag = mon_cfg.get("amazon_associate_tag", "YOUR_AMAZON_TAG-20")
    encoded_q = urllib.parse.quote_plus(search_keywords)
    return f"https://{domain}/s?k={encoded_q}&tag={tag}"


def discover_autocomplete_dtcs():
    found = []
    prefixes = ["p04", "p01", "p03", "p00", "p21", "u01"]
    for pref in prefixes:
        try:
            q = f"{pref} code "
            url = f"http://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q={urllib.parse.quote(q)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data[1]:
                    match = re.search(r"\b([pbcduPBCDU][0-9]{4})\b", item)
                    if match:
                        code = match.group(1).upper()
                        clean_desc = re.sub(r"\b" + code + r"\b", "", item, flags=re.IGNORECASE).strip()
                        clean_desc = re.sub(r"\b(code|meaning|fix|symptoms|cost)\b", "", clean_desc, flags=re.IGNORECASE).strip()
                        title_str = f"{code} {clean_desc.title()}".strip()
                        if len(title_str) >= 5:
                            found.append(title_str)
        except Exception as e:
            print(f"[WARN] Autocomplete discovery notice: {e}")
    return found


def build_fallback_dtc_data(dtc_topic):
    """Mesin cadangan otomatis (Deterministic ASE Mechanic Engine) jika API Gemini limit/offline."""
    match = re.search(r"\b([pbcduPBCDU][0-9]{4})\b", dtc_topic)
    code = match.group(1).upper() if match else "P0420"
    definition = re.sub(r"\b" + code + r"\b", "", dtc_topic, flags=re.IGNORECASE).strip()
    if not definition:
        definition = "Powertrain Control Module Diagnostic Circuit Performance"

    low_def = definition.lower()
    if "catalyst" in low_def or "o2" in low_def or "heated" in low_def:
        part1 = ("Upstream & Downstream Oxygen (O2) Sensor", "60%", "$42 - $115", f"{code} Oxygen O2 Sensor OEM Replacement", "Always apply anti-seize compound to threads and torque to 30 ft-lbs.")
        part2 = ("Direct-Fit Catalytic Converter & Gasket Kit", "30%", "$160 - $420", f"{code} Direct Fit Catalytic Converter", "Inspect exhaust manifold for hairline cracks before bolting in new converter.")
        part3 = ("7/8 Inch (22mm) Offset Oxygen Sensor Socket Wrench", "10%", "$11 - $22", "22mm Oxygen Sensor Socket Offset Wrench Tool", "Use a slotted offset socket so you do not pinch or sever the sensor pigtail harness.")
        avg_part = 95
        labor_hrs = 1.5
        severity = "Moderate"
    elif "misfire" in low_def or "cylinder" in low_def:
        part1 = ("Direct Ignition Coil Pack & Boot Set", "55%", "$35 - $110", f"{code} Ignition Coil Pack OEM Set", "Swap the suspect coil to an adjacent cylinder first to see if the misfire code follows.")
        part2 = ("Double Iridium Spark Plugs (Pre-Gapped)", "35%", "$28 - $68", "Double Iridium Spark Plugs Set", "Verify gap with a wire feeler gauge and apply dielectric grease inside the coil boot.")
        part3 = ("Fuel Injector & Combustion Chamber Cleaner", "10%", "$14 - $29", "High Mileage Fuel Injector Cleaner PEA", "Run a full tank with PEA-based cleaner to clear carbon deposits on intake valves.")
        avg_part = 65
        labor_hrs = 1.0
        severity = "High"
    elif "evap" in low_def or "leak" in low_def or "purge" in low_def:
        part1 = ("EVAP Canister Purge Control Solenoid Valve", "55%", "$24 - $65", f"{code} EVAP Canister Purge Valve Solenoid", "Blow through the disconnected purge valve; if air passes when unpowered, it is stuck open.")
        part2 = ("OEM Fuel Tank Gas Cap with Tether", "30%", "$15 - $32", "OEM Replacement Fuel Gas Cap Seal", "Inspect the rubber O-ring seal for dry rot and click tighten until it ratchets.")
        part3 = ("EVAP Charcoal Canister Vent Solenoid", "15%", "$35 - $85", f"{code} EVAP Vent Control Valve Solenoid", "Check under-vehicle vent hose for spider webs or mud blockage.")
        avg_part = 45
        labor_hrs = 1.0
        severity = "Moderate"
    elif "lean" in low_def or "mass" in low_def or "air" in low_def:
        part1 = ("Mass Air Flow (MAF) Sensor Assembly", "50%", "$48 - $130", f"{code} Mass Air Flow Sensor OEM", "Check live PID airflow grams/sec at warm idle (should roughly match engine displacement in liters).")
        part2 = ("PCV Valve & Intake Vacuum Hose Kit", "35%", "$18 - $45", "PCV Valve Vacuum Hose Replacement Kit", "Listen for hissing around the intake plenum and accordion boot while engine idles.")
        part3 = ("Mass Air Flow Sensor & Throttle Body Cleaner Spray", "15%", "$12 - $22", "CRC Mass Air Flow Sensor Cleaner Spray", "Never touch the delicate platinum hot-wire with fingers; spray 10-15 bursts and air dry.")
        avg_part = 75
        labor_hrs = 1.0
        severity = "Moderate"
    else:
        part1 = (f"OEM {definition} Sensor / Actuator", "65%", "$45 - $135", f"{code} {definition} Replacement Sensor", "Inspect the 3-pin or 4-pin weatherpack connector for green corrosion before installing.")
        part2 = ("Weatherpack Wiring Pigtail Harness Repair Kit", "25%", "$16 - $38", f"{code} Automotive Sensor Pigtail Connector Harness", "Use heat-shrink solder sleeves rather than twist-on crimps for accurate ECU voltage readings.")
        part3 = ("Electronic Contact Cleaner & Dielectric Grease Kit", "10%", "$12 - $24", "Automotive Electrical Contact Cleaner Dielectric Grease", "Flush terminal pins and verify 5.0V reference signal with a digital multimeter.")
        avg_part = 85
        labor_hrs = 1.5
        severity = "Moderate"

    return {
        "dtc_code": code,
        "official_definition": definition,
        "seo_title": f"Code {code}: {definition} — Symptoms, Causes & Repair Cost (2026)",
        "meta_description": f"Complete mechanic diagnostic guide for OBD-II code {code} ({definition}). Compare DIY vs shop repair costs and find exact replacement parts.",
        "severity_level": severity,
        "drivability_verdict": f"Driving short distances with {code} active is generally possible if the Check Engine Light is steady, but flashing MIL or severe drivability loss requires immediate inspection to prevent costly component damage.",
        "cost_estimator": {
            "avg_part_cost_usd": avg_part,
            "estimated_labor_hours": labor_hrs,
            "default_shop_hourly_rate": 135,
            "diy_difficulty": "Intermediate"
        },
        "symptoms": [
            f"Illuminated Check Engine Light (MIL) storing trouble code {code} in ECM memory",
            "Noticeable drop in fuel economy (2 to 4 MPG reduction) due to open-loop fuel trim compensation",
            "Hesitation, rough idle, or stumble during cold start and light-throttle acceleration",
            "Failed state emissions / smog readiness monitor inspection"
        ],
        "replacement_parts": [
            {
                "part_name": part1[0],
                "failure_probability": part1[1],
                "avg_price_range": part1[2],
                "amazon_search_keywords": part1[3],
                "replacement_tip": part1[4]
            },
            {
                "part_name": part2[0],
                "failure_probability": part2[1],
                "avg_price_range": part2[2],
                "amazon_search_keywords": part2[3],
                "replacement_tip": part2[4]
            },
            {
                "part_name": part3[0],
                "failure_probability": part3[1],
                "avg_price_range": part3[2],
                "amazon_search_keywords": part3[3],
                "replacement_tip": part3[4]
            }
        ],
        "diagnostic_steps": [
            {
                "step_title": f"Scan Freeze-Frame Data & Live Sensor PIDs for {code}",
                "instruction": f"Plug in an OBD2 scan tool and record the exact engine RPM, coolant temperature, and short/long-term fuel trims (STFT/LTFT) when {code} triggered.",
                "required_tool": "Bluetooth OBD2 Scanner"
            },
            {
                "step_title": "Verify 5V Reference, Ground & Signal Integrity with Multimeter",
                "instruction": "Backprobe the sensor harness connector with ignition ON (engine OFF). Confirm a steady 5.0V reference voltage, less than 0.5 Ohms resistance to chassis ground, and no shorted signal wire.",
                "required_tool": "Digital Automotive Multimeter"
            },
            {
                "step_title": "Replace Faulty Component & Reset ECM Adaptive Tables",
                "instruction": f"Install the replacement component to factory torque specifications, clear code {code} using your OBD2 reader, and complete a 20-minute highway/city drive cycle to verify readiness monitors.",
                "required_tool": "Automotive Ratchet & Socket Set"
            }
        ],
        "common_affected_vehicles": [
            f"Ford F-150, Escape, and Explorer (High mileage sensor thermal fatigue triggering {code})",
            f"Toyota Camry, Corolla, and RAV4 (OEM sensor aging or vacuum/exhaust seal degradation)",
            f"Chevrolet Silverado, Equinox, and Malibu (Connector corrosion or actuator sticking)",
            f"Honda Civic, Accord, and CR-V (Strict ECM threshold sensitivity above 85,000 miles)"
        ],
        "faqs": [
            {
                "q": f"Can I pass an emissions test with code {code} active?",
                "a": f"No. Any active Check Engine Light or pending {code} trouble code automatically fails state OBD-II emissions inspections until the fault is repaired and readiness monitors complete."
            },
            {
                "q": f"Will disconnecting the battery clear code {code} permanently?",
                "a": f"Disconnecting the negative battery terminal only erases volatile memory temporarily. Once the ECM runs two consecutive self-test drive cycles and detects the underlying fault, {code} will immediately return."
            },
            {
                "q": f"How much does a repair shop charge to fix {code} in 2026?",
                "a": f"Most dealerships and independent shops charge between $240 and $520 for {code} diagnosis and labor, whereas ordering the replacement part online and installing it yourself typically costs under ${avg_part}."
            }
        ]
    }


def generate_dtc_guide(dtc_topic):
    """Mencoba Gemini API terlebih dahulu; jika gagal/limit, otomatis beralih ke Fallback Engine."""
    if not GEMINI_API_KEY:
        print("[INFO] GEMINI_API_KEY kosong, menggunakan Built-in ASE Mechanic Engine.")
        return build_fallback_dtc_data(dtc_topic)

    prompt = f"""
You are an ASE Master Certified Automotive Technician. Create a comprehensive 2026 diagnostic, repair cost, and replacement part guide for OBD-II Trouble Code: "{dtc_topic}".
Return ONLY a valid JSON object matching this exact schema:
{{
  "dtc_code": "Exact 5-character code e.g. P0420",
  "official_definition": "Official SAE/OBD-II definition of the code",
  "seo_title": "Code [DTC_CODE]: Meaning, Symptoms, Causes & DIY Replacement Cost (2026)",
  "meta_description": "Complete master mechanic guide for [DTC_CODE]. Calculate DIY vs shop repair costs, test sensors with a multimeter, and find exact replacement parts.",
  "severity_level": "Moderate / High / Critical",
  "drivability_verdict": "Short 2-sentence advice on whether it is safe to keep driving with this code active.",
  "cost_estimator": {{
    "avg_part_cost_usd": 85,
    "estimated_labor_hours": 1.5,
    "default_shop_hourly_rate": 130,
    "diy_difficulty": "Beginner / Intermediate / Advanced"
  }},
  "symptoms": ["Symptom 1", "Symptom 2", "Symptom 3", "Symptom 4"],
  "replacement_parts": [
    {{
      "part_name": "Primary most likely faulty part name",
      "failure_probability": "65%",
      "avg_price_range": "$45 - $140",
      "amazon_search_keywords": "Exact search query to buy this automotive part on Amazon",
      "replacement_tip": "1-sentence mechanic tip"
    }},
    {{
      "part_name": "Secondary likely faulty part name",
      "failure_probability": "25%",
      "avg_price_range": "$25 - $80",
      "amazon_search_keywords": "Exact search query to buy this automotive part on Amazon",
      "replacement_tip": "1-sentence mechanic tip"
    }},
    {{
      "part_name": "Third related tool or component",
      "failure_probability": "10%",
      "avg_price_range": "$12 - $35",
      "amazon_search_keywords": "Exact search query to buy this automotive tool/part on Amazon",
      "replacement_tip": "1-sentence mechanic tip"
    }}
  ],
  "diagnostic_steps": [
    {{
      "step_title": "Step 1 title",
      "instruction": "Detailed technical instruction with exact specs.",
      "required_tool": "Bluetooth OBD2 Scanner"
    }},
    {{
      "step_title": "Step 2 title",
      "instruction": "Detailed technical instruction with exact pinout/voltage specs.",
      "required_tool": "Digital Automotive Multimeter"
    }},
    {{
      "step_title": "Step 3 title",
      "instruction": "Detailed technical instruction on replacement and clearing codes.",
      "required_tool": "Ratchet & Sensor Socket Set"
    }}
  ],
  "common_affected_vehicles": ["Vehicle 1", "Vehicle 2", "Vehicle 3"],
  "faqs": [
    {{"q": "Question 1?", "a": "Answer 1."}},
    {{"q": "Question 2?", "a": "Answer 2."}},
    {{"q": "Question 3?", "a": "Answer 3."}}
  ]
}}
"""

    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    for model_name in models:
        try:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.25,
                    "responseMimeType": "application/json"
                }
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=35) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                raw_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)
                return json.loads(raw_text)
        except Exception as e:
            print(f"[WARN] Gemini ({model_name}) notice for '{dtc_topic}': {e}")

    print(f"[FALLBACK] Menggunakan Built-in ASE Mechanic Engine untuk '{dtc_topic}'.")
    return build_fallback_dtc_data(dtc_topic)


def safe_number(val, default=85):
    try:
        cleaned = re.sub(r"[^0-9.]", "", str(val))
        return float(cleaned) if cleaned else float(default)
    except Exception:
        return float(default)


def build_dtc_html_page(data, slug, mon_cfg):
    code = str(data.get("dtc_code", "P0420")).upper()
    ce = data.get("cost_estimator", {})
    avg_part_cost = int(safe_number(ce.get("avg_part_cost_usd", 85), 85))
    default_rate = int(safe_number(ce.get("default_shop_hourly_rate", 130), 130))
    labor_hours = round(safe_number(ce.get("estimated_labor_hours", 1.5), 1.5), 1)
    diy_diff = ce.get("diy_difficulty", "Intermediate")

    scanner_cfg = mon_cfg.get("featured_scanner", {})
    scanner_url = build_amazon_url(scanner_cfg.get("search_query", "OBD2+Scanner"), mon_cfg)

    schema_graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "HowTo",
                "name": f"How to Diagnose and Fix {code}: {data.get('official_definition', '')}",
                "description": data.get("meta_description", ""),
                "estimatedCost": {
                    "@type": "MonetaryAmount",
                    "currency": "USD",
                    "value": str(avg_part_cost)
                },
                "step": [
                    {
                        "@type": "HowToStep",
                        "name": s.get("step_title", "Diagnostic Step"),
                        "text": s.get("instruction", "")
                    } for s in data.get("diagnostic_steps", [])
                ]
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": f.get("q", ""),
                        "acceptedAnswer": {"@type": "Answer", "text": f.get("a", "")}
                    } for f in data.get("faqs", [])
                ]
            }
        ]
    }

    parts_html = ""
    for p in data.get("replacement_parts", []):
        amz_url = build_amazon_url(f"{code} {p.get('amazon_search_keywords', p.get('part_name', ''))}", mon_cfg)
        parts_html += f"""
        <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex flex-col justify-between hover:border-amber-500/50 transition">
          <div>
            <div class="flex items-center justify-between gap-2 mb-2">
              <span class="text-xs font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2.5 py-0.5 rounded">Fix Probability: {p.get('failure_probability', '50%')}</span>
              <span class="text-sm font-bold text-emerald-400">{p.get('avg_price_range', '$35 - $110')}</span>
            </div>
            <h3 class="text-lg font-bold text-white mt-2">{p.get('part_name', 'OEM Replacement Sensor')}</h3>
            <p class="text-xs text-zinc-400 mt-2 leading-relaxed">🔧 <strong>Tech Tip:</strong> {p.get('replacement_tip', '')}</p>
          </div>
          <a href="{amz_url}" target="_blank" rel="nofollow sponsored" class="mt-5 block text-center bg-amber-500 hover:bg-amber-400 text-zinc-950 font-extrabold py-2.5 px-4 rounded-lg text-sm transition shadow-lg">
            Check Part Price on Amazon →
          </a>
        </div>"""

    symptoms_html = "".join([
        f"<li class='flex items-center gap-2.5 bg-zinc-900/80 border border-zinc-800 px-4 py-3 rounded-lg text-sm text-zinc-200'><span class='text-red-400 font-bold'>●</span> {sym}</li>"
        for sym in data.get("symptoms", [])
    ])

    steps_html = ""
    for idx, st in enumerate(data.get("diagnostic_steps", []), start=1):
        tool_name = st.get("required_tool", "OBD2 Scanner")
        tool_url = build_amazon_url(tool_name, mon_cfg)
        steps_html += f"""
        <label class="flex items-start gap-4 bg-zinc-900 border border-zinc-800 rounded-xl p-5 cursor-pointer hover:border-zinc-700 transition">
          <input type="checkbox" class="mt-1.5 w-5 h-5 accent-amber-500 rounded cursor-pointer diag-check" data-step="{idx}">
          <div class="flex-1">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-base font-bold text-white">Step {idx}: {st.get('step_title', '')}</h3>
              <a href="{tool_url}" target="_blank" rel="nofollow sponsored" class="text-xs text-amber-400 hover:underline font-semibold">Required Tool: {tool_name} ↗</a>
            </div>
            <p class="text-sm text-zinc-300 mt-2 leading-relaxed">{st.get('instruction', '')}</p>
          </div>
        </label>"""

    vehicles_html = "".join([
        f"<li class='border-b border-zinc-800 py-3 text-sm text-zinc-300 last:border-0'>🚘 {v}</li>"
        for v in data.get("common_affected_vehicles", [])
    ])

    faqs_html = "".join([
        f"<div class='bg-zinc-900 border border-zinc-800 rounded-xl p-5'><h3 class='font-bold text-white text-base mb-2'>{f.get('q', '')}</h3><p class='text-sm text-zinc-300 leading-relaxed'>{f.get('a', '')}</p></div>"
        for f in data.get("faqs", [])
    ])

    canonical_url = f"{SITE_BASE_URL}/{slug}.html"

    html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{data.get('seo_title', code)}</title>
  <meta name="description" content="{data.get('meta_description', '')}">
  <link rel="canonical" href="{canonical_url}">
  <meta property="og:title" content="{data.get('seo_title', code)}">
  <meta property="og:description" content="{data.get('meta_description', '')}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical_url}">
  <script src="https://cdn.tailwindcss.com"></script>
  <script type="application/ld+json">{json.dumps(schema_graph)}</script>
</head>
<body class="bg-zinc-950 text-zinc-100 antialiased min-h-screen flex flex-col">
  <header class="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur sticky top-0 z-30">
    <div class="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
      <a href="index.html" class="text-lg font-black tracking-tight text-white flex items-center gap-2">
        <span class="bg-amber-500 text-zinc-950 px-2 py-0.5 rounded font-black">OBD2</span>RepairIndex
      </a>
      <a href="{scanner_url}" target="_blank" rel="nofollow sponsored" class="text-xs sm:text-sm bg-amber-500 hover:bg-amber-400 text-zinc-950 font-extrabold px-3.5 py-2 rounded-lg transition">
        {scanner_cfg.get('cta_text', 'Check OBD2 Scanner Price on Amazon →')}
      </a>
    </div>
  </header>

  <main class="max-w-5xl mx-auto px-4 py-10 flex-1 w-full">
    <div class="mb-8">
      <div class="flex flex-wrap items-center gap-2.5 mb-3">
        <span class="text-xs font-extrabold uppercase tracking-widest bg-amber-500 text-zinc-950 px-3 py-1 rounded-full">DTC {code}</span>
        <span class="text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/20 px-3 py-1 rounded-full">Severity: {data.get('severity_level', 'Moderate')}</span>
        <span class="text-xs font-semibold bg-zinc-800 text-zinc-300 px-3 py-1 rounded-full">DIY Level: {diy_diff}</span>
      </div>
      <h1 class="text-3xl sm:text-4xl font-black text-white leading-tight">{data.get('seo_title', code)}</h1>
      <p class="text-amber-400 font-mono text-sm mt-2">Official SAE Definition: "{data.get('official_definition', '')}"</p>
      <div class="mt-4 bg-zinc-900 border-l-4 border-amber-500 p-4 rounded-r-xl text-sm text-zinc-200 leading-relaxed">
        <strong>Master Mechanic Verdict:</strong> {data.get('drivability_verdict', '')}
      </div>
    </div>

    <!-- REPLACEMENT PARTS & AMAZON MONETIZATION GRID -->
    <section class="mb-12">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-2xl font-extrabold text-white">Most Likely Replacement Parts for {code}</h2>
        <span class="text-xs text-zinc-400">Verified OEM & Aftermarket Fitment</span>
      </div>
      <div class="grid md:grid-cols-3 gap-5">{parts_html}</div>
    </section>

    <!-- INTERACTIVE DIY VS MECHANIC LABOR CALCULATOR -->
    <section class="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 sm:p-8 mb-12 shadow-2xl">
      <h2 class="text-xl font-extrabold text-white mb-2">Interactive {code} Repair Cost & DIY Savings Calculator</h2>
      <p class="text-xs text-zinc-400 mb-6">Adjust your local mechanic shop hourly rate and vehicle complexity to calculate how much you save by replacing the part yourself.</p>
      <div class="grid md:grid-cols-2 gap-8 items-center">
        <div class="space-y-5">
          <div>
            <div class="flex justify-between text-sm font-medium mb-1.5">
              <label for="rateSlider" class="text-zinc-300">Local Mechanic / Dealership Labor Rate ($/hr)</label>
              <span class="text-amber-400 font-bold">$<span id="rateVal">{default_rate}</span>/hr</span>
            </div>
            <input id="rateSlider" type="range" min="75" max="250" step="5" value="{default_rate}" class="w-full accent-amber-500 cursor-pointer">
          </div>

          <div>
            <div class="flex justify-between text-sm font-medium mb-1.5">
              <label for="hoursSlider" class="text-zinc-300">Estimated Book Labor Hours</label>
              <span class="text-amber-400 font-bold"><span id="hoursVal">{labor_hours}</span> hrs</span>
            </div>
            <input id="hoursSlider" type="range" min="0.5" max="6.0" step="0.5" value="{labor_hours}" class="w-full accent-amber-500 cursor-pointer">
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="bg-zinc-950 border border-zinc-800 rounded-xl p-4">
            <span class="text-xs uppercase text-zinc-400 font-bold">Repair Shop Total</span>
            <div class="text-2xl sm:text-3xl font-black text-red-400 mt-1">$<span id="shopTotal">0</span></div>
            <p class="text-xs text-zinc-500 mt-1">Includes parts + shop markup + labor</p>
          </div>
          <div class="bg-zinc-950 border border-emerald-500/30 rounded-xl p-4">
            <span class="text-xs uppercase text-emerald-400 font-bold">DIY at Home Cost</span>
            <div class="text-2xl sm:text-3xl font-black text-emerald-400 mt-1">$<span id="diyTotal">{avg_part_cost}</span></div>
            <p class="text-xs text-zinc-500 mt-1">Ordering part directly online</p>
          </div>
        </div>
      </div>

      <div class="mt-6 bg-emerald-950/40 border border-emerald-500/30 rounded-xl p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div class="text-sm text-emerald-200 font-medium">
          💰 Doing this repair yourself saves you <strong class="text-emerald-400 text-base">$<span id="netSavings">0</span></strong> in mechanic labor fees!
        </div>
        <a href="{scanner_url}" target="_blank" rel="nofollow sponsored" class="shrink-0 bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-extrabold px-4 py-2 rounded-lg text-xs uppercase tracking-wider transition">
          Clear {code} With OBD2 Scanner →
        </a>
      </div>
    </section>

    <!-- SYMPTOMS -->
    <section class="mb-12">
      <h2 class="text-2xl font-extrabold text-white mb-4">Common {code} Symptoms</h2>
      <ul class="grid sm:grid-cols-2 gap-3">{symptoms_html}</ul>
    </section>

    <!-- INTERACTIVE STEP-BY-STEP DIAGNOSTIC CHECKLIST -->
    <section class="mb-12">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-2xl font-extrabold text-white">Step-by-Step Mechanic Testing Checklist</h2>
        <span id="progressBadge" class="text-xs font-bold bg-zinc-800 text-amber-400 px-3 py-1 rounded-full">0 / 3 Completed</span>
      </div>
      <div class="space-y-4">{steps_html}</div>
    </section>

    <!-- AFFECTED VEHICLES -->
    <section class="mb-12 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
      <h2 class="text-xl font-extrabold text-white mb-3">Vehicles Most Prone to Code {code}</h2>
      <ul>{vehicles_html}</ul>
    </section>

    <!-- FAQ -->
    <section class="mb-12">
      <h2 class="text-2xl font-extrabold text-white mb-5">Frequently Asked Questions ({code})</h2>
      <div class="space-y-4">{faqs_html}</div>
    </section>
  </main>

  <footer class="border-t border-zinc-800 py-8 text-center text-xs text-zinc-500 px-4">
    <p>© {datetime.now(timezone.utc).year} OBD2RepairIndex. Independent Automotive Diagnostic Database. As an Amazon Associate, we earn from qualifying purchases.</p>
  </footer>

  <script>
    const partCost = {avg_part_cost};
    const rateSlider = document.getElementById('rateSlider');
    const hoursSlider = document.getElementById('hoursSlider');
    const rateVal = document.getElementById('rateVal');
    const hoursVal = document.getElementById('hoursVal');
    const shopTotalEl = document.getElementById('shopTotal');
    const netSavingsEl = document.getElementById('netSavings');

    function updateCosts() {{
      const rate = parseFloat(rateSlider.value);
      const hours = parseFloat(hoursSlider.value);
      rateVal.textContent = rate;
      hoursVal.textContent = hours.toFixed(1);

      const shopPartsMarkup = Math.round(partCost * 1.35);
      const laborCost = Math.round(rate * hours);
      const totalShop = shopPartsMarkup + laborCost;
      const savings = Math.max(0, totalShop - partCost);

      shopTotalEl.textContent = totalShop.toLocaleString();
      netSavingsEl.textContent = savings.toLocaleString();
    }}

    rateSlider.addEventListener('input', updateCosts);
    hoursSlider.addEventListener('input', updateCosts);
    updateCosts();

    const checks = document.querySelectorAll('.diag-check');
    const badge = document.getElementById('progressBadge');
    checks.forEach(ch => {{
      ch.addEventListener('change', () => {{
        const done = Array.from(checks).filter(c => c.checked).length;
        badge.textContent = `${{done}} / ${{checks.length}} Completed`;
      }});
    }});
  </script>
</body>
</html>"""

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, f"{slug}.html"), "w", encoding="utf-8") as f:
        f.write(html)


def rebuild_portal_sitemap_and_rss(published, mon_cfg):
    scanner_cfg = mon_cfg.get("featured_scanner", {})
    scanner_url = build_amazon_url(scanner_cfg.get("search_query", "OBD2+Scanner"), mon_cfg)

    cards_html = ""
    for item in reversed(published):
        cards_html += f"""
        <a href="{item['slug']}.html" class="block bg-zinc-900 border border-zinc-800 hover:border-amber-500/60 rounded-xl p-5 transition group">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-black uppercase bg-amber-500 text-zinc-950 px-2.5 py-0.5 rounded">{item['code']}</span>
            <span class="text-xs text-zinc-400">{item.get('severity', 'Moderate')}</span>
          </div>
          <h2 class="text-base font-bold text-white group-hover:text-amber-400 transition">{item['official_definition']}</h2>
          <p class="text-xs text-zinc-400 mt-2 line-clamp-2">{item['description']}</p>
          <span class="inline-block mt-4 text-xs font-extrabold text-amber-400">View Replacement Parts & Cost Calculator →</span>
        </a>"""

    index_html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OBD2RepairIndex — Check Engine Trouble Code Lookup & Replacement Part Finder (2026)</title>
  <meta name="description" content="Instant OBD-II trouble code lookup. Calculate DIY vs mechanic repair costs, test sensors, and find exact replacement parts.">
  <link rel="canonical" href="{SITE_BASE_URL}/">
  <link rel="alternate" type="application/rss+xml" title="OBD2RepairIndex RSS Feed" href="{SITE_BASE_URL}/rss.xml">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen flex flex-col">
  <header class="border-b border-zinc-800 bg-zinc-900/80 sticky top-0 z-30 backdrop-blur">
    <div class="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
      <div class="text-lg font-black text-white flex items-center gap-2">
        <span class="bg-amber-500 text-zinc-950 px-2 py-0.5 rounded font-black">OBD2</span>RepairIndex
      </div>
      <a href="{scanner_url}" target="_blank" rel="nofollow sponsored" class="text-xs sm:text-sm bg-amber-500 hover:bg-amber-400 text-zinc-950 font-extrabold px-3.5 py-2 rounded-lg transition">
        {scanner_cfg.get('cta_text', 'Check OBD2 Scanner Price on Amazon →')}
      </a>
    </div>
  </header>

  <main class="max-w-5xl mx-auto px-4 py-12 flex-1 w-full">
    <div class="text-center max-w-2xl mx-auto mb-10">
      <h1 class="text-3xl sm:text-5xl font-black text-white tracking-tight">OBD-II Trouble Code & Auto-Part Database</h1>
      <p class="text-zinc-400 mt-3 text-base sm:text-lg">Enter your 5-digit Check Engine Light code (e.g. P0420, P0171, P0300) to calculate repair costs and locate exact replacement sensors.</p>
      <div class="mt-6">
        <input id="filterInput" type="text" placeholder="Search by DTC Code or Symptom (e.g. P0420, Catalyst, Lean, Misfire...)" class="w-full bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-3.5 text-sm text-white focus:outline-none focus:border-amber-500">
      </div>
    </div>

    <div id="codeGrid" class="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">{cards_html}</div>
  </main>

  <footer class="border-t border-zinc-800 py-8 text-center text-xs text-zinc-500">
    <p>© {datetime.now(timezone.utc).year} OBD2RepairIndex. As an Amazon Associate, we earn from qualifying purchases.</p>
  </footer>

  <script>
    const filterInput = document.getElementById('filterInput');
    const cards = Array.from(document.getElementById('codeGrid').children);
    filterInput.addEventListener('input', (e) => {{
      const q = e.target.value.toLowerCase();
      cards.forEach(c => {{
        c.style.display = c.textContent.toLowerCase().includes(q) ? 'block' : 'none';
      }});
    }});
  </script>
</body>
</html>"""

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls_xml = f"""  <url>
    <loc>{SITE_BASE_URL}/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>\n"""

    for item in published:
        urls_xml += f"""  <url>
    <loc>{SITE_BASE_URL}/{item['slug']}.html</loc>
    <lastmod>{item.get('date', today)}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.9</priority>
  </url>\n"""

    with open(os.path.join(DOCS_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls_xml}</urlset>""")

    rss_items = ""
    for item in list(reversed(published))[:30]:
        rss_items += f"""    <item>
      <title>{item['title']}</title>
      <link>{SITE_BASE_URL}/{item['slug']}.html</link>
      <guid>{SITE_BASE_URL}/{item['slug']}.html</guid>
      <description>{item['description']}</description>
    </item>\n"""

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>OBD2RepairIndex Diagnostic Database</title>
    <link>{SITE_BASE_URL}/</link>
    <description>Latest OBD-II Trouble Code Repair Guides and Part Calculators</description>
    <atom:link href="{SITE_BASE_URL}/rss.xml" rel="self" type="application/rss+xml" />
    <atom:link href="https://pubsubhubbub.appspot.com/" rel="hub" />
{rss_items}  </channel>
</rss>"""

    with open(os.path.join(DOCS_DIR, "rss.xml"), "w", encoding="utf-8") as f:
        f.write(rss_xml)

    with open(os.path.join(DOCS_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE_URL}/sitemap.xml\n")

    with open(os.path.join(DOCS_DIR, f"{INDEXNOW_KEY}.txt"), "w", encoding="utf-8") as f:
        f.write(INDEXNOW_KEY)


def notify_search_engines(new_urls):
    if not SITE_BASE_URL or not new_urls:
        return
    parsed_host = urllib.parse.urlparse(SITE_BASE_URL).netloc
    payload = {
        "host": parsed_host,
        "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE_BASE_URL}/{INDEXNOW_KEY}.txt",
        "urlList": new_urls
    }
    try:
        req = urllib.request.Request(
            "https://api.indexnow.org/indexnow",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[INDEXNOW] Pushed {len(new_urls)} URLs (HTTP {resp.status})")
    except Exception as e:
        print(f"[WARN] IndexNow ping notice: {e}")

    try:
        hub_data = urllib.parse.urlencode({
            "hub.mode": "publish",
            "hub.url": f"{SITE_BASE_URL}/rss.xml"
        }).encode("utf-8")
        req_hub = urllib.request.Request(
            "https://pubsubhubbub.appspot.com/",
            data=hub_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        with urllib.request.urlopen(req_hub, timeout=15) as resp_hub:
            print(f"[WEBSUB] Google PubSubHubbub ping status: {resp_hub.status}")
    except Exception as e:
        print(f"[WARN] WebSub ping notice: {e}")


def main():
    published = load_json(PUBLISHED_FILE, [])
    mon_cfg = load_json(MONETIZATION_FILE, {})
    published_codes = {item["code"].upper() for item in published}

    candidates = []
    if CUSTOM_DTC:
        candidates.append(CUSTOM_DTC)
    candidates.extend(SEED_DTCS)
    candidates.extend(discover_autocomplete_dtcs())

    new_urls = []
    count = 0

    for item_str in candidates:
        if count >= PAGES_PER_RUN:
            break
        match = re.search(r"\b([pbcduPBCDU][0-9]{4})\b", item_str)
        if not match:
            continue
        code_id = match.group(1).upper()
        if code_id in published_codes:
            continue

        print(f"[ENGINE] Building diagnostic guide for DTC {code_id} ({item_str})...")
        try:
            data = generate_dtc_guide(item_str)
            slug = slugify(f"{code_id}-{data['official_definition']}-fix-cost")
            build_dtc_html_page(data, slug, mon_cfg)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            published.append({
                "code": code_id,
                "slug": slug,
                "official_definition": data["official_definition"],
                "title": data["seo_title"],
                "description": data["meta_description"],
                "severity": data.get("severity_level", "Moderate"),
                "date": today
            })
            published_codes.add(code_id)
            if SITE_BASE_URL:
                new_urls.append(f"{SITE_BASE_URL}/{slug}.html")
            count += 1
            time.sleep(2)
        except Exception as e:
            print(f"[ERROR] Failed on {code_id}: {e}")

    save_json(PUBLISHED_FILE, published)
    rebuild_portal_sitemap_and_rss(published, mon_cfg)
    if new_urls and SITE_BASE_URL:
        new_urls.append(f"{SITE_BASE_URL}/")
        notify_search_engines(new_urls)
    print(f"[DONE] Successfully published {count} new OBD-II diagnostic pages.")


if __name__ == "__main__":
    main()
