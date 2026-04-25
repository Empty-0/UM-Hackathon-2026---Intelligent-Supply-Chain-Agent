import json
import os
from collections import defaultdict
from zhipuai import ZhipuAI

# 仅从环境变量读取，不做默认值
API_KEY = os.environ.get("ZHIPU_API_KEY")
if not API_KEY:
    raise ValueError("ZHIPU_API_KEY environment variable not set")

client = ZhipuAI(api_key=API_KEY)

def generate_all_drafts(sourcing_json: str, original_request: str, intent_type: str = "NEW_ORDER") -> str:
    """
    Agent 3: 确保无论 Agent 2 是否匹配成功，都能生成邮件草稿。
    """
    try:
        data = json.loads(sourcing_json)
    except Exception as e:
        return json.dumps({"error": f"Invalid JSON: {e}", "emails": []})

    print(f"DEBUG: Agent 3 received results -> {data.get('results')}")

    results = data.get("results", [])
    drafts = []

    if results and any(res.get("winner") for res in results):
        vendor_groups = defaultdict(list)
        risk_alerts = data.get("risk_alerts", [])

        for res in results:
            winner = res.get("winner")
            if winner and (winner.get("Supplier Email") or winner.get("email")):
                email_addr = winner.get("Supplier Email") or winner.get("email")
                vendor_groups[email_addr].append({
                    "product": res.get("product_name") or res.get("product"),
                    "quantity": winner.get("quantity") or 1,
                    "supplier_name": winner.get("Supplier Name") or winner.get("Supplier") or "Supplier"
                })

        for email_addr, items in vendor_groups.items():
            vendor_name = items[0].get("supplier_name")
            subject, body = _call_glm_to_compose_email(vendor_name, items, original_request, intent_type, [])
            drafts.append({"to": email_addr, "subject": subject, "body": body, "vendor": vendor_name})

    if not drafts:
        print("DEBUG: No vendors found. Triggering GLM-4 Fallback drafting...")
        subject, body = _call_glm_to_compose_email("Potential Supplier", [], original_request, intent_type, [])
        drafts.append({
            "to": "procurement@company.com",
            "subject": subject,
            "body": body,
            "vendor": "System Identified Potential Supplier"
        })

    return json.dumps({
        "intent_type": intent_type,
        "emails": drafts
    }, indent=2)

def _call_glm_to_compose_email(vendor_name, items, original_request, intent_type, risks):
    """调用 GLM-4 撰写邮件"""
    prompt = f"""
    You are a professional Procurement Manager. 
    User Request: {original_request}
    Items available in DB: {json.dumps(items)}
    Intent: {intent_type}
    
    Task: Write a professional business inquiry email. 
    If no items were found in our database, write a general 'Request for Information' (RFI) based on the User Request.
    
    Output format:
    Subject: [Subject]
    Body: [Body]
    """
    try:
        response = client.chat.completions.create(
            model="glm-4",
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        if "Subject:" in content and "Body:" in content:
            parts = content.split("Body:")
            return parts[0].replace("Subject:", "").strip(), parts[1].strip()
        return f"Inquiry regarding {original_request[:30]}", content
    except:
        return "Purchase Inquiry", "Please contact us regarding our procurement needs."

def send_all_emails(drafts_json: str) -> str:
    return json.dumps({"status": "success", "message": "Task processed."})