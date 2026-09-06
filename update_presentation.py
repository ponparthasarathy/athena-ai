import os
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

prs_path = "SIH2026-IDEA-Presentation-Format (1).pptx"
out_path = "SIH2026_Athena_Perfect10_Presentation.pptx"

prs = pptx.Presentation(prs_path)

# Image paths
img_slide2_dash = r"C:\Users\nanth\.gemini\antigravity-ide\brain\057212ec-f82a-4cc7-87c5-3ef292eefd9a\athena_live_dashboard_screenshot_1788602113764.png"
img_slide3_flow = r"e:\athena-ai-main\athena_flowchart_vector.png"
img_slide5_impact = r"C:\Users\nanth\.gemini\antigravity-ide\brain\057212ec-f82a-4cc7-87c5-3ef292eefd9a\athena_minimalist_impact_1788595066400.png"
img_qr_code = r"e:\athena-ai-main\athena_live_demo_qr.png"

def clear_added_pictures(slide, max_keep=1):
    pics = [s for s in slide.shapes if s.shape_type == pptx.enum.shapes.MSO_SHAPE_TYPE.PICTURE]
    for p in pics[max_keep:]:
        sp = p._element
        sp.getparent().remove(sp)

# ==========================================================
# SLIDE 2: IDEA TITLE & PROOF OF CONCEPT (Dashboard Screenshot + Built Features)
# ==========================================================
slide2 = prs.slides[1]

tb2 = None
for s in slide2.shapes:
    if s.has_text_frame and ("Detailed explanation" in s.text_frame.text or "PROPOSED SOLUTION" in s.text_frame.text):
        tb2 = s
        break

if tb2:
    tb2.left = Inches(0.4)
    tb2.top = Inches(1.1)
    tb2.width = Inches(5.8)
    tb2.height = Inches(5.0)
    
    tf = tb2.text_frame
    tf.word_wrap = True
    tf.clear()
    
    p = tf.paragraphs[0]
    p.text = "PROPOSED SOLUTION & PROOF OF CONCEPT"
    p.font.bold = True
    p.font.size = Pt(14)
    p.font.color.rgb = RGBColor(220, 220, 220)
    
    points = [
        ("Hybrid Edge-Cloud Architecture", "ESP32 edge sensors (MAX30102, BME280, MPU6050) compute on-device fused risk score locally; Google Gemini 2.5 Flash provides clinical advisory when connected."),
        ("Built Multi-Disaster Engine (Heat, Floods & Pollution)", "Active code detects Heat Index hazards, BME280 pressure drops (<1005 hPa) & humidity (>90%) for flash floods, plus atmospheric inversion math for air pollution smog alerts."),
        ("Privacy-Preserving Architecture (Zero PII)", "Raw 50Hz PPG & IMU motion streams stay inside ESP32 SRAM. Only anonymized risk indices pass over TLS 1.2 encrypted MQTT (Port 8883) to stateless Gemini AI—zero PII stored or sent."),
        ("Live 3D Digital Twin Dashboard", "Three.js motion visualizer on web dashboard reflects real-time patient physical posture and fall status via WebSockets.")
    ]
    
    for title, desc in points:
        p_item = tf.add_paragraph()
        p_item.space_before = Pt(5)
        
        run_t = p_item.add_run()
        run_t.text = f"•  {title}: "
        run_t.font.bold = True
        run_t.font.size = Pt(10.5)
        run_t.font.color.rgb = RGBColor(255, 255, 255)
        
        run_d = p_item.add_run()
        run_d.text = desc
        run_d.font.size = Pt(9.5)
        run_d.font.color.rgb = RGBColor(200, 200, 200)

# Insert Live 3D Dashboard Screenshot on Slide 2 Right Side
clear_added_pictures(slide2, max_keep=1)
if os.path.exists(img_slide2_dash):
    slide2.shapes.add_picture(
        img_slide2_dash,
        left=Inches(6.4),
        top=Inches(1.3),
        width=Inches(6.3),
        height=Inches(4.6)
    )

# ==========================================================
# SLIDE 3: TECHNICAL APPROACH (Accurate Flowchart + Security Layer)
# ==========================================================
slide3 = prs.slides[2]

tb3 = None
for s in slide3.shapes:
    if s.has_text_frame and ("Technologies to be used" in s.text_frame.text or "CORE HARDWARE" in s.text_frame.text):
        tb3 = s
        break

if tb3:
    tb3.left = Inches(0.4)
    tb3.top = Inches(1.1)
    tb3.width = Inches(12.4)
    tb3.height = Inches(1.8)
    
    tf = tb3.text_frame
    tf.word_wrap = True
    tf.clear()
    
    p = tf.paragraphs[0]
    p.text = "CORE HARDWARE, SOFTWARE & SECURITY STACK"
    p.font.bold = True
    p.font.size = Pt(15)
    p.font.color.rgb = RGBColor(220, 220, 220)
    
    tech_bullets = [
        "Edge Hardware & Sensing: ESP32 Dev Module + MAX30102 (Heart Rate/SpO2), BME280 (Temp/Humidity/Barometer), MPU6050 (50Hz IMU), SSD1306 OLED Display.",
        "Privacy & Transport Security: On-device SRAM feature extraction (zero PII) + TLS 1.2 encrypted HiveMQ MQTT + FastAPI Async Backend.",
        "Cloud AI & Visualization: Google Gemini 2.5 Flash API for clinical advisory + Three.js WebSockets 3D Digital Twin Avatar."
    ]
    for b in tech_bullets:
        p_item = tf.add_paragraph()
        p_item.space_before = Pt(4)
        run = p_item.add_run()
        run.text = f"•  {b}"
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(200, 200, 200)

# Replace/Insert Slide 3 Vector Flowchart Image
clear_added_pictures(slide3, max_keep=1)
if os.path.exists(img_slide3_flow):
    slide3.shapes.add_picture(
        img_slide3_flow,
        left=Inches(0.4),
        top=Inches(3.0),
        width=Inches(12.4),
        height=Inches(3.3)
    )

# ==========================================================
# SLIDE 4: FEASIBILITY, VIABILITY & MATRIX (Comparative Matrix)
# ==========================================================
slide4 = prs.slides[3]

tb4 = None
for s in slide4.shapes:
    if s.has_text_frame and ("Analysis of the feasibility" in s.text_frame.text or "FEASIBILITY" in s.text_frame.text):
        if s.left < Inches(1.0) and s.top < Inches(2.0):
            tb4 = s
            break

if tb4:
    tb4.left = Inches(0.4)
    tb4.top = Inches(1.1)
    tb4.width = Inches(12.4)
    tb4.height = Inches(1.3)
    tf = tb4.text_frame
    tf.word_wrap = True
    tf.clear()
    
    p = tf.paragraphs[0]
    p.text = "FEASIBILITY ANALYSIS & COMPARATIVE MATRIX"
    p.font.bold = True
    p.font.size = Pt(14)
    p.font.color.rgb = RGBColor(220, 220, 220)
    
    feasibility_notes = [
        "Feasibility: Off-the-shelf components fully integrated in working prototype with live FastAPI cloud server and 3D web dashboard.",
        "Built Feature Coverage: 50Hz Fall Detection, Heat Index Math, BME280 Flood Barometric Drop & Air Pollution Smog Risk rules active in codebase."
    ]
    for fn in feasibility_notes:
        p_item = tf.add_paragraph()
        p_item.space_before = Pt(3)
        run = p_item.add_run()
        run.text = f"•  {fn}"
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(200, 200, 200)

for s in list(slide4.shapes):
    if s.has_table:
        sp = s._element
        sp.getparent().remove(sp)

rows, cols = 7, 3
left, top, width, height = Inches(0.4), Inches(2.5), Inches(12.4), Inches(3.8)
table_shape = slide4.shapes.add_table(rows, cols, left, top, width, height)
table = table_shape.table

table.columns[0].width = Inches(3.2)
table.columns[1].width = Inches(4.4)
table.columns[2].width = Inches(4.8)

table_data = [
    ["COMPARISON CRITERIA", "EXISTING COMMERCIAL WEARABLES (Fitbit, Apple Watch)", "ATHENA HEALTH ECOSYSTEM"],
    ["Offline Fall & Risk Detection", "Cloud-dependent / Server-side processing", "100% On-Device Edge Processing (50Hz IMU Algorithm)"],
    ["Privacy & Biometric Isolation", "Centralized cloud data sync of health history", "On-Device Biometric Isolation + TLS 1.2 (Zero PII)"],
    ["Multi-Disaster Risk Sensing", "None (Only internal temp / ambient noise)", "Built BME280 Heat Index, Flood Barometer & Pollution Rules"],
    ["Real-Time Patient Visualization", "Static 2D Summary Graphs & HR Charts", "Live 3D Digital Twin Avatar (Three.js WebSockets)"],
    ["Clinical AI Advisory Integration", "Fixed rule-based app notifications", "LLM Triage Engine (Google Gemini 2.5 Flash API)"],
    ["Operational Network Resilience", "Suspends monitoring without active phone/app sync", "Local OLED Visual Status & Automatic Data Re-Sync on Reconnect"]
]

for row_idx, row in enumerate(table_data):
    for col_idx, text in enumerate(row):
        cell = table.cell(row_idx, col_idx)
        cell.text = text
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        
        if row_idx == 0:
            p.font.bold = True
            p.font.size = Pt(11)
            p.font.color.rgb = RGBColor(255, 255, 255)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(30, 35, 45)
        else:
            p.font.size = Pt(9.5)
            if col_idx == 0:
                p.font.bold = True
                p.font.color.rgb = RGBColor(230, 230, 230)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(22, 25, 30)
            elif col_idx == 1:
                p.font.color.rgb = RGBColor(180, 180, 180)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(25, 28, 35)
            else:
                p.font.bold = True
                p.font.color.rgb = RGBColor(255, 255, 255)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(18, 40, 32)

# ==========================================================
# SLIDE 5: IMPACT AND BENEFITS
# ==========================================================
slide5 = prs.slides[4]

tb5 = None
for s in slide5.shapes:
    if s.has_text_frame and ("Potential impact" in s.text_frame.text or "MEASURABLE IMPACT" in s.text_frame.text):
        tb5 = s
        break

if tb5:
    tb5.left = Inches(0.4)
    tb5.top = Inches(1.2)
    tb5.width = Inches(5.8)
    tb5.height = Inches(4.8)
    
    tf = tb5.text_frame
    tf.word_wrap = True
    tf.clear()
    
    p = tf.paragraphs[0]
    p.text = "MEASURABLE IMPACT & BENEFIT CATEGORIES"
    p.font.bold = True
    p.font.size = Pt(15)
    p.font.color.rgb = RGBColor(220, 220, 220)
    
    impact_items = [
        ("Social Impact", "Protects vulnerable groups (elderly, outdoor laborers, chronic patients) with real-time fall detection and environmental heat risk warnings delivered to caregivers via the cloud dashboard."),
        ("Economic Viability", "Built using accessible off-the-shelf modular hardware components, lowering deployment cost barriers compared to clinical-grade proprietary monitors."),
        ("Environmental & Energy", "Edge-first computation processes high-rate 50Hz sensor data locally, only streaming compact telemetry JSON over MQTT, significantly reducing cloud data transmission and energy footprint.")
    ]
    for cat, desc in impact_items:
        p_item = tf.add_paragraph()
        p_item.space_before = Pt(10)
        
        run_t = p_item.add_run()
        run_t.text = f"•  {cat}: "
        run_t.font.bold = True
        run_t.font.size = Pt(12)
        run_t.font.color.rgb = RGBColor(255, 255, 255)
        
        run_d = p_item.add_run()
        run_d.text = desc
        run_d.font.size = Pt(11)
        run_d.font.color.rgb = RGBColor(200, 200, 200)

clear_added_pictures(slide5, max_keep=1)
if os.path.exists(img_slide5_impact):
    slide5.shapes.add_picture(
        img_slide5_impact,
        left=Inches(6.4),
        top=Inches(1.5),
        width=Inches(6.3),
        height=Inches(4.4)
    )

# ==========================================================
# SLIDE 6: RESEARCH, REFERENCES & LIVE DEMO QR CODE
# ==========================================================
slide6 = prs.slides[5]

tb6 = None
for s in slide6.shapes:
    if s.has_text_frame and ("RESEARCH" in s.text_frame.text or "[1] WHO" in s.text_frame.text):
        tb6 = s
        break

if tb6:
    tb6.left = Inches(0.4)
    tb6.top = Inches(1.1)
    tb6.width = Inches(8.5)
    tb6.height = Inches(4.9)
    
    tf = tb6.text_frame
    tf.word_wrap = True
    tf.clear()
    
    p = tf.paragraphs[0]
    p.text = "ACADEMIC & GOVERNMENT REFERENCES"
    p.font.bold = True
    p.font.size = Pt(14)
    p.font.color.rgb = RGBColor(220, 220, 220)
    
    refs = [
        ("[1] WHO — Heat and Health (who.int)", "Grounds heat-stress detection in documented public health risk."),
        ("[2] NDMA — Heat Wave Guidelines, Govt of India (ndma.gov.in)", "Supports disaster resilience during extreme climate events directly from PS requirements."),
        ("[3] Ayushman Bharat Digital Mission (abdm.gov.in)", "Aligns Athena with India's push toward accessible, low-cost digital healthcare."),
        ("[4] Existing Wearables Gap Analysis", "Fitbit / Apple Watch assume constant connectivity; Athena solves offline disaster monitoring."),
        ("[5] Athena — Live Cloud Prototype", "https://athena-ai-13ci.onrender.com/ (Publicly viewable live dashboard)")
    ]
    for tag, desc in refs:
        p_item = tf.add_paragraph()
        p_item.space_before = Pt(6)
        
        run_t = p_item.add_run()
        run_t.text = f"{tag}\n"
        run_t.font.bold = True
        run_t.font.size = Pt(11)
        run_t.font.color.rgb = RGBColor(255, 255, 255)
        
        run_d = p_item.add_run()
        run_d.text = f"→ {desc}"
        run_d.font.size = Pt(10)
        run_d.font.color.rgb = RGBColor(190, 190, 190)

clear_added_pictures(slide6, max_keep=1)
if os.path.exists(img_qr_code):
    slide6.shapes.add_picture(
        img_qr_code,
        left=Inches(9.3),
        top=Inches(1.8),
        width=Inches(2.5),
        height=Inches(2.5)
    )
    
    qr_box = slide6.shapes.add_textbox(Inches(9.0), Inches(4.4), Inches(3.0), Inches(1.2))
    tf_qr = qr_box.text_frame
    tf_qr.word_wrap = True
    p_qr = tf_qr.paragraphs[0]
    p_qr.alignment = PP_ALIGN.CENTER
    p_qr.text = "SCAN TO ACCESS LIVE DEMO\nathena-ai-13ci.onrender.com"
    p_qr.font.bold = True
    p_qr.font.size = Pt(10)
    p_qr.font.color.rgb = RGBColor(255, 255, 255)

# Save Presentation
try:
    prs.save(out_path)
    print(f"Presentation successfully updated and saved to '{out_path}'.")
except Exception as e:
    print(f"Error saving to {out_path}: {e}")

try:
    prs.save(prs_path)
    print(f"Original template also updated at '{prs_path}'.")
except Exception as e:
    print(f"Note: Could not overwrite '{prs_path}' (file may be open in PowerPoint). Saved output to '{out_path}'.")
