"""Bộ Truy Xuất Tri Thức RAG (Retrieval-Augmented Generation) sử dụng Google Embedding API (`gemini-embedding-001`).

Chức năng:
1. Lưu trữ cơ sở tri thức chuẩn về:
   - Định danh & Tác giả: Trợ lý ảo do Nguyễn Tuấn Anh tạo ra.
   - Quy định phân quyền 3 tầng (Tầng 1: Admin Nguyễn Tuấn Anh, Tầng 2: Thành viên gia đình có bể lệnh riêng, Tầng 3: Khách).
   - Khả năng, giới hạn an toàn và sơ đồ thiết bị phần cứng.
2. Nhúng (Embed) các mục tri thức bằng model `gemini-embedding-001` (vector 3072 chiều) thông qua `GEMINI_API_KEY`
   và lưu cache xuống `simulator/data/knowledge_embeddings_cache.json` để truy xuất tức thì.
3. Tìm kiếm tương đồng ngữ nghĩa (Cosine Similarity trên Vector 3072 chiều kết hợp Keyword Boost)
   để trả về câu trả lời ngắn gọn, đủ ý, không lễ nghi hay nịnh bợ.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

import numpy as np
from dotenv import load_dotenv
from google import genai

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

KB_FILE = DATA_DIR / "knowledge_base.json"
CACHE_FILE = DATA_DIR / "knowledge_embeddings_cache.json"
EMBED_MODEL = "gemini-embedding-001"
KB_VERSION = "3.0-CONCISE-QA-AND-TIER-POLICY"

DEFAULT_KNOWLEDGE_ITEMS: list[dict[str, str]] = [
    {
        "id": "identity_and_creator",
        "min_tier": "3",
        "topic": "Bạn là ai / Ai tạo ra bạn",
        "keywords": "bạn là ai, tên gì, giới thiệu, ai tạo ra, ai làm ra, ai lập trình, tác giả, người tạo, chủ nhân, nguyễn tuấn anh",
        "content": (
            "Tôi là trợ lý ảo điều khiển nhà thông minh do Nguyễn Tuấn Anh tạo ra."
        ),
    },
    {
        "id": "capabilities_what_can_you_do",
        "min_tier": "3",
        "topic": "Bạn được làm những gì và có thể làm những gì",
        "keywords": "làm được gì, có thể làm những gì, được làm những gì, chức năng, khả năng, nhiệm vụ, công dụng",
        "content": (
            "Tôi là trợ lý ảo do Nguyễn Tuấn Anh tạo ra, có thể làm 5 việc chính: "
            "1) Điều khiển 6 thiết bị gồm cửa chính, đèn khách, đèn ngủ, quạt, điều hòa, còi báo động. "
            "2) Hẹn giờ 1 lần hoặc lặp hàng ngày, hàng tuần theo giây, phút, giờ, AM/PM và ngày tháng. "
            "3) Học đổi từ, đổi lệnh và đặt luật IF-ELSE theo bể riêng của từng thành viên. "
            "4) Thu âm phân tích giọng nói và quản lý phân quyền 3 tầng. "
            "5) Truy vấn bể lệnh, bể hẹn giờ và thực hiện 4 chế độ reset theo đúng cấp quyền."
        ),
    },
    {
        "id": "alarm_siren_meaning",
        "min_tier": "3",
        "topic": "Còi báo động ở đây nghĩa là gì / dùng để làm gì",
        "keywords": "còi báo động, coi bao dong, báo động, còi hú, siren, nghĩa là gì, dùng làm gì",
        "content": (
            "Còi báo động là thiết bị phát âm thanh cảnh báo an ninh hoặc báo động khẩn cấp trong nhà."
        ),
    },
    {
        "id": "voice_enrollment_flow",
        "min_tier": "2",
        "topic": "Cách thêm người mới / thu âm giọng nói để cấp quyền cấp 2, cấp 3",
        "keywords": "thêm người mới, bật ghi âm, thu âm, ghi âm, cấp quyền giọng nói, đăng ký giọng",
        "content": (
            "Khi bạn yêu cầu thu âm cấp quyền, tôi sẽ đếm 3, 2, 1 và nháy đèn báo hiệu bắt đầu, thu âm trong 5 giây, báo đã thu âm đủ, phân tích tần số giọng nói rồi hỏi tên người được cấp quyền."
        ),
    },
    {
        "id": "three_tier_rules",
        "min_tier": "2",
        "topic": "Quy định phân quyền 3 tầng (Tầng 1 Admin Nguyễn Tuấn Anh, Tầng 2 Thành viên, Tầng 3 Khách)",
        "keywords": "quy định, phân quyền, 3 tầng, ba tầng, cấp quyền, hủy quyền, tầng 1, tầng 2, tầng 3, cấp 1, cấp 2, cấp 3, admin, thành viên, khách",
        "content": (
            "Hệ thống có 3 tầng quyền hạn: "
            "Tầng 1 là Admin tối cao Nguyễn Tuấn Anh: toàn quyền, được hỏi mọi thông tin, luật IF áp dụng toàn nhà, không ai được hủy người do Tầng 1 cấp, và không ai được đè hay vướng hẹn giờ của Tầng 1. "
            "Tầng 2 là Thành viên gia đình: mỗi người có bể lệnh và hẹn giờ riêng, chỉ được reset bể của chính mình, được thu âm cấp và hủy quyền cho Tầng 3 (trừ người do Tầng 1 cấp), không được hủy cùng cấp. "
            "Tầng 3 là Khách: chỉ được gọi lệnh đóng mở cố định, không được đổi lệnh, không được đặt luật IF, không được hẹn giờ và không được cấp hay hủy quyền của ai."
        ),
    },
    {
        "id": "hardware_devices_gpio",
        "min_tier": "1",
        "topic": "Danh sách thiết bị và sơ đồ chân phần cứng GPIO ESP32-S3 của hệ thống",
        "keywords": "sơ đồ chân, phần cứng, esp32, gpio, mấy thiết bị, danh sách thiết bị",
        "content": (
            "Nhà gồm 6 thiết bị: Cửa chính, Đèn phòng khách, Đèn phòng ngủ, Quạt trần, Điều hòa và Còi báo động."
        ),
    },
]


def ensure_kb_file() -> list[dict[str, str]]:
    if KB_FILE.exists():
        try:
            raw = json.loads(KB_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("version") == KB_VERSION and isinstance(raw.get("items"), list):
                return raw["items"]
        except Exception:
            pass
    payload = {"version": KB_VERSION, "items": DEFAULT_KNOWLEDGE_ITEMS}
    KB_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return list(DEFAULT_KNOWLEDGE_ITEMS)


class SmartHomeKnowledgeRAG:
    """Bộ RAG sử dụng Google Embedding (`gemini-embedding-001`) để trả lời ngắn gọn về trợ lý ảo và quy định 3 tầng."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.items: list[dict[str, str]] = ensure_kb_file()
        self.embeddings: dict[str, list[float]] = {}
        self._load_or_build_embeddings()

    def _doc_text_for_embedding(self, item: dict[str, str]) -> str:
        return f"{item.get('topic', '')} | {item.get('keywords', '')} | {item.get('content', '')}"

    def _load_or_build_embeddings(self) -> None:
        sig = {it["id"]: self._doc_text_for_embedding(it) for it in self.items}
        if CACHE_FILE.exists():
            try:
                cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                if (
                    cached.get("version") == KB_VERSION
                    and cached.get("model") == EMBED_MODEL
                    and cached.get("signatures") == sig
                ):
                    self.embeddings = cached.get("vectors", {})
                    if len(self.embeddings) == len(self.items):
                        return
            except Exception:
                pass

        if not self.client:
            return

        try:
            texts = [self._doc_text_for_embedding(it) for it in self.items]
            resp = self.client.models.embed_content(model=EMBED_MODEL, contents=texts)
            vecs: dict[str, list[float]] = {}
            for it, emb in zip(self.items, resp.embeddings):
                vecs[it["id"]] = list(emb.values)
            self.embeddings = vecs
            CACHE_FILE.write_text(
                json.dumps(
                    {
                        "version": KB_VERSION,
                        "model": EMBED_MODEL,
                        "dimension": len(next(iter(vecs.values()), [])),
                        "signatures": sig,
                        "vectors": vecs,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        va = np.asarray(a, dtype=np.float32)
        vb = np.asarray(b, dtype=np.float32)
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if denom < 1e-9:
            return 0.0
        return float(np.dot(va, vb) / denom)

    def retrieve(
        self,
        query: str,
        current_tier: int = 1,
        query_permission_mode: str = "tier_restricted",
        top_k: int = 1,
    ) -> dict[str, Any]:
        """Truy xuất đoạn tri thức khớp nhất bằng Google Embedding (`gemini-embedding-001`) + Cosine Similarity.
        Kiểm tra phân quyền hỏi theo cấp (`tier_restricted` vs `open_all`).
        """
        q_clean = query.strip()
        if not q_clean:
            return {
                "ok": False,
                "error": "Câu hỏi trống.",
            }

        q_vec: list[float] | None = None
        if self.client and self.embeddings:
            try:
                r = self.client.models.embed_content(model=EMBED_MODEL, contents=[q_clean])
                q_vec = list(r.embeddings[0].values)
            except Exception:
                q_vec = None

        q_low = q_clean.lower()
        scored: list[tuple[float, dict[str, str]]] = []
        for it in self.items:
            sem_score = 0.0
            if q_vec is not None and it["id"] in self.embeddings:
                sem_score = self._cosine(q_vec, self.embeddings[it["id"]])

            kw_bonus = 0.0
            for kw in it.get("keywords", "").split(","):
                kw_s = kw.strip().lower()
                if kw_s and kw_s in q_low:
                    kw_bonus += 0.25

            scored.append((sem_score + kw_bonus, it))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_it = scored[0]
        min_tier_allowed = int(best_it.get("min_tier", "3"))

        # Kiểm tra giới hạn quyền hỏi theo từng tầng (nếu Tầng 1 chưa mở quyền hỏi 'open_all' cho tất cả)
        if query_permission_mode != "open_all" and current_tier > min_tier_allowed:
            deny_msg = f"Bạn đang ở Cấp {current_tier}, chỉ được hỏi các thông tin thuộc phạm vi phân quyền của cấp mình."
            return {
                "ok": False,
                "error": deny_msg,
                "exact_spoken_reply": deny_msg,
                "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{deny_msg}'",
                "summary": deny_msg,
            }

        top_matches = [
            {
                "id": it["id"],
                "topic": it["topic"],
                "score": round(float(sc), 4),
                "content": it["content"],
            }
            for sc, it in scored[: max(1, top_k)]
        ]

        concise_answer = top_matches[0]["content"]
        return {
            "ok": True,
            "matched_id": best_it["id"],
            "embedding_model": EMBED_MODEL,
            "vector_dim": len(q_vec) if q_vec else 0,
            "matches": top_matches,
            "exact_spoken_reply": concise_answer,
            "instruction_for_ai": (
                f"Dựa trên dữ liệu '{concise_answer}', chỉ trả lời ĐÚNG ý câu hỏi của người dùng trong 1 câu ngắn gọn, KHÔNG kể lể dài dòng những phần không được hỏi."
            ),
            "summary": concise_answer,
        }

    def upsert_knowledge_item(
        self,
        topic: str,
        content: str,
        keywords: str = "",
        min_tier: int = 3,
        current_tier: int = 1,
    ) -> dict[str, Any]:
        """Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) dạy thêm hoặc sửa nội dung RAG bằng giọng nói và nhúng vector ngay."""
        if current_tier > 1:
            msg = "Từ chối truy cập! Chỉ Admin Cấp 1 Nguyễn Tuấn Anh mới có quyền thêm hoặc sửa tri thức RAG bằng giọng nói."
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        t_clean = (topic or "").strip()
        c_clean = (content or "").strip()
        if not t_clean or not c_clean:
            return {"ok": False, "error": "Chủ đề và nội dung tri thức không được để trống."}

        import re
        slug = "custom_" + (re.sub(r"[^a-z0-9_]+", "_", t_clean.lower()).strip("_") or "item")
        kw_clean = (keywords or t_clean).strip()
        new_item = {
            "id": slug,
            "topic": t_clean,
            "min_tier": str(max(1, min(int(min_tier or 3), 3))),
            "keywords": kw_clean,
            "content": c_clean,
        }

        replaced = False
        for idx, it in enumerate(self.items):
            if it["id"] == slug or it["topic"].strip().lower() == t_clean.lower():
                new_item["id"] = it["id"]
                self.items[idx] = new_item
                replaced = True
                break
        if not replaced:
            self.items.append(new_item)

        if self.client:
            try:
                resp = self.client.models.embed_content(
                    model=EMBED_MODEL, contents=[self._doc_text_for_embedding(new_item)]
                )
                self.embeddings[new_item["id"]] = list(resp.embeddings[0].values)
            except Exception:
                pass

        spoken = f"Đã cập nhật vào bộ nhớ tri thức chủ đề '{t_clean}'."
        return {
            "ok": True,
            "item": new_item,
            "exact_spoken_reply": spoken,
            "instruction_for_ai": f"BẮT BUỘC trả lời ngắn gọn đúng câu: '{spoken}'",
            "message": spoken,
        }

    def reset_custom_knowledge(self) -> None:
        self.items = ensure_kb_file()
        self._load_or_build_embeddings()
