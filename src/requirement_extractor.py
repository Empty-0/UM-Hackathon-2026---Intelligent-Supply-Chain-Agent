import json
import os
from zhipuai import ZhipuAI

# 配置你的 API Key
# 建议：如果是演示现场，直接写死在这里；如果想更专业，可以用 os.environ.get("ZHIPU_API_KEY")
API_KEY = "82eff1d7e5e04d8182563072a428d063.E4T49tzSmw5ezjii"
client = ZhipuAI(api_key=API_KEY)

def extract_requirements(user_input: str) -> str:
    """
    Agent 1: 利用 GLM-4 彻底取代脆弱的正则提取逻辑。
    它负责理解语义、识别语言并输出结构化的采购 JSON。
    """
    print(f"--- GLM-4 Parsing Input: {user_input} ---")
    
    # 构建 Prompt，强制要求返回符合你系统格式的 JSON
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
            model="glm-4", # 明确使用 GLM-4
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} # 确保返回的是 JSON
        )
        
        result_json = response.choices[0].message.content
        print(f"GLM-4 Output: {result_json}")
        return result_json

    except Exception as e:
        print(f"Error calling GLM-4: {e}")
        # 兜底逻辑：如果 API 失败，返回一个最简单的格式，防止整个 pipeline 崩溃
        return json.dumps({
            "intent_type": "NEW_ORDER",
            "original_language": "en",
            "items": [{"product": user_input, "quantity": 1, "detected_category": "General"}]
        })