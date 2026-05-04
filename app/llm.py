from __future__ import annotations

import re

import httpx

from app.settings import get_settings


SYSTEM_PROMPT = """你是京东帮助问答助手。
你只能使用给定资料中的事实回答用户问题，但不要在回答中提到“FAQ”“资料”“根据内容”“根据文档”等依据说明。
如果给定资料中没有答案，必须回答“暂未找到相关答案”，不能编造。
不能回答订单、物流、账号、支付、退款状态等个人化查询问题。
不能承诺具体业务结果。
回答要直接、简洁、准确，开头不要写“根据……”或“基于……”。"""


class DeepSeek:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.status = "not_called"

    def configured(self) -> bool:
        return bool(self.settings.deepseek_api_key and self.settings.deepseek_base_url and self.settings.deepseek_model)

    async def generate(self, query: str, evidences: list[dict]) -> str:
        if not self.configured():
            self.status = "not_configured"
            return extractive_answer(evidences)
        try:
            async with httpx.AsyncClient(timeout=self.settings.deepseek_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
                    json={
                        "model": self.settings.deepseek_model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": build_prompt(query, evidences)},
                        ],
                        "temperature": 0.2,
                    },
                )
                response.raise_for_status()
                self.status = "ok"
                return clean_answer(response.json()["choices"][0]["message"]["content"])
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return extractive_answer(evidences)


def build_prompt(query: str, docs: list[dict]) -> str:
    evidence = []
    for index, doc in enumerate(docs, start=1):
        evidence.append(
            "\n".join(
                [
                    f"[材料 {index}]",
                    f"问题：{doc.get('question', '')}",
                    f"答案：{doc.get('answer', '')}",
                    f"边界：{doc.get('answer_boundary') or doc.get('answerBoundary') or ''}",
                    f"来源：{doc.get('source_url') or doc.get('sourceUrl') or ''}",
                ]
            )
        )
    return f"""用户问题：
{query}

可用事实：
{chr(10).join(evidence)}

请直接回答用户问题。
要求：
1. 不要使用给定事实之外的信息。
2. 如果资料不足，直接说明暂未找到相关答案。
3. 不要编造来源。
4. 不要提到“FAQ”“资料”“文档”“根据内容”“根据以上信息”等内部依据表述。
5. 输出适合用户阅读的中文回答。"""


def clean_answer(answer: str) -> str:
    text = str(answer or "").strip()
    evidence_words = r"(?:FAQ内容|FAQ资料|FAQ文档|FAQ信息|FAQ|资料|材料|文档|内容|信息|事实)"
    patterns = (
        rf"^根据(?:以上|上述|提供的|给定的)?{evidence_words}[，,：:\s]*",
        rf"^基于(?:以上|上述|提供的|给定的)?{evidence_words}[，,：:\s]*",
        rf"^从(?:以上|上述|提供的|给定的)?{evidence_words}(?:来看|可知)?[，,：:\s]*",
        rf"^按(?:以上|上述|提供的|给定的)?{evidence_words}[，,：:\s]*",
    )
    previous = None
    while text and text != previous:
        previous = text
        for pattern in patterns:
            text = re.sub(pattern, "", text, count=1).lstrip()
    return text or "暂未找到相关答案。"


def extractive_answer(evidences: list[dict]) -> str:
    if not evidences:
        return "暂未找到相关答案。"
    answer = str(evidences[0].get("answer") or "").strip()
    return answer or "暂未找到相关答案。"
