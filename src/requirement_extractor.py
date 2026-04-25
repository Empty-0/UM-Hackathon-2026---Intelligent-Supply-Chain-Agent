import json
import os
from zhipuai import ZhipuAI

# 仅从环境变量读取，不做默认值
API_KEY = os.environ.get("ZHIPU_API_KEY")
if not API_KEY:
    raise ValueError("ZHIPU_API_KEY environment variable not set")

client = ZhipuAI(api_key=API_KEY)

def extract_requirements(user_input: str) -> str:
    """
    Agent 1: 利用 GLM-4 彻底取代脆弱的正则提取逻辑。
    它负责理解语义、识别语言并输出结构化的采购 JSON。
    """
    print(f"--- GLM-4 Parsing Input: {user_input} ---")
    
    prompt = f"""
    You are a Procurement Specialist AI. 
    Analyze the user's procurement request and extract structured details.
    
    User Input: "{user_input}"
    
    Constraints:
    1. Detect language (en, ms, or zh).
    2. Extract products and their quantities.
    3. Identify if it's a NEW_ORDER or an UPDATE (correction).
    4. Categorize items (e.g., Electronics, Fashion, F&B, Medicine).
    5. Check if Halal is specifically mentioned.

    Return ONLY a valid JSON object in this format:
    {{
      "intent_type": "NEW_ORDER",
      "original_language": "ms",
      "items": [
        {{
          "product": "Product Name",
          "quantity": 10,
          "max_price": null,
          "lead_time_days": null,
          "detected_category": "Category Name",
          "halal_required": false
        }}
      ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="glm-4",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        result_json = response.choices[0].message.content
        print(f"GLM-4 Output: {result_json}")
        return result_json

    except Exception as e:
        print(f"Error calling GLM-4: {e}")
        return json.dumps({
            "intent_type": "NEW_ORDER",
            "original_language": "en",
            "items": [{"product": user_input, "quantity": 1, "detected_category": "General"}]
        })