"""Module simulator.auth.invite_and_gmail_mixin: Quản lý Email Allowlist, Link Mời Phân Cấp, Gửi/Đọc Gmail OTP và Thu Hồi Quyền Giọng Nói."""

from __future__ import annotations

import base64
import copy
import email.utils
import json
import os
import random
import re
import secrets
import smtplib
import subprocess
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from simulator.auth.constants_and_crypto import (
    DEFAULT_INVITE_LINKS,
    ROOT_DIR,
    _now_vn,
    build_reading_prompt,
    canonical_gmail_mailbox,
    hash_password,
    strict_single_email_ascii,
)
from simulator.voice_config import (
    OWNER_EMAIL,
    OWNER_ID,
    THRESHOLD_DEEP,
    THRESHOLD_MEL,
)

HARDCODED_REAL_EMAIL_ALLOWLIST: set[str] = {
    "nep94121@gmail.com",
}

SMTP_TIMEOUT_SECONDS: float = float(os.environ.get("SMTP_TIMEOUT_SECONDS", "8.0"))


def is_email_allowlisted_for_real_send(email: str | None) -> bool:
    """Kiểm tra email có thuộc danh sách cho phép gửi thư thật hay không (chỉ nep94121@gmail.com và alias Gmail hợp lệ)."""
    clean = strict_single_email_ascii(email)
    if not clean:
        return False
    canon = canonical_gmail_mailbox(clean)
    owner_canon = canonical_gmail_mailbox(OWNER_EMAIL) or "nep94121@gmail.com"
    if canon and canon == owner_canon:
        return True
    if os.environ.get("VERCEL"):
        return False
    hardcoded_canon = {canonical_gmail_mailbox(item) or item.lower() for item in HARDCODED_REAL_EMAIL_ALLOWLIST}
    if canon and canon in hardcoded_canon:
        return True
    env_allowlist: set[str] = set()
    env_val = os.environ.get("REAL_EMAIL_ALLOWLIST", "").strip()
    if env_val:
        for raw_part in re.split(r"[,;:\s]+", env_val):
            item = strict_single_email_ascii(raw_part)
            if item:
                env_allowlist.add(item)
    return clean in env_allowlist


is_real_email_allowed = is_email_allowlisted_for_real_send


class AuthInviteGmailMixin:
    """Mixin xử lý Email Allowlist, Phân cấp Link Mời, Google OAuth + Gmail OTP, Thu âm Trang đầu và Xóa/Bật quyền bằng giọng nói."""

    accounts: list[dict[str, Any]]
    family_email_allowlist: dict[str, dict[str, Any]]
    invite_links: dict[str, dict[str, Any]]
    pending_invite_registrations: dict[str, dict[str, Any]]

    def add_family_email(
        self,
        actor_id: str,
        target_email: str,
        target_tier: int,
        source: str = "Web/App",
    ) -> dict[str, Any]:
        """Thêm Email Gia Đình (Email Allowlist) theo phân quyền 3 tầng."""
        def _mutate() -> dict[str, Any]:
            actor = self.find_account(actor_id)
            if not actor:
                return {"ok": False, "error": f"Không tìm thấy tài khoản người thêm '{actor_id}'!", "status_code": 404}

            actor_tier = int(actor.get("tier", 3))
            tier_int = int(target_tier)

            if actor_tier != 1:
                msg = "Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền thêm thành viên hoặc cấp quyền!"
                self._log_event(
                    layer="Email Allowlist",
                    action=f"add_email_blocked_tier{actor_tier}",
                    email=actor["email"],
                    status="FAIL",
                    detail=f"Cấp {actor_tier} ({actor['display_name']}) cố thêm email {target_email} vào Cấp {tier_int} -> BỊ CHẶN.",
                    source=source,
                )
                return {
                    "ok": False,
                    "status_code": 403,
                    "rbac_blocked": True,
                    "error": msg,
                }

            if not actor.get("permission_active", True):
                return {
                    "ok": False,
                    "status_code": 403,
                    "rbac_blocked": True,
                    "error": f"🚫 Tài khoản {actor['display_name']} hiện đang bị thu hồi quyền, không thể thêm thành viên!",
                }

            if tier_int not in (2, 3):
                msg = "Cấp 1 chỉ có quyền thêm Cấp 2 hoặc Cấp 3"
                return {"ok": False, "status_code": 403, "rbac_blocked": True, "error": msg}

            clean_email = target_email.strip().lower()
            if not clean_email or "@" not in clean_email:
                return {"ok": False, "error": "Địa chỉ email không hợp lệ!", "status_code": 400}

            existing_acc = self.find_account(clean_email)
            if existing_acc:
                existing_tier = int(existing_acc.get("tier", 99))
                if existing_tier == 1:
                    msg = "Không thể hạ cấp hoặc thay đổi tài khoản Chủ nhà Cấp 1"
                    self._log_event(
                        layer="Email Allowlist",
                        action="add_email_blocked_c1_override",
                        email=actor["email"],
                        status="FAIL",
                        detail=f"Tài khoản {actor['display_name']} (Cấp {actor_tier}) cố thay đổi tài khoản Chủ nhà Cấp 1 ({clean_email}) -> BỊ CHẶN.",
                        source=source,
                    )
                    return {"ok": False, "error": msg, "status_code": 403}
                if actor_tier >= existing_tier:
                    msg = "Không có quyền sửa đổi tài khoản có cấp bậc cao hơn hoặc bằng"
                    self._log_event(
                        layer="Email Allowlist",
                        action="add_email_blocked_privilege_escalation",
                        email=actor["email"],
                        status="FAIL",
                        detail=f"Tài khoản {actor['display_name']} (Cấp {actor_tier}) không có quyền sửa đổi tài khoản {clean_email} (Cấp {existing_tier}) -> BỊ CHẶN.",
                        source=source,
                    )
                    return {"ok": False, "error": msg, "status_code": 403}

            previous_accounts = copy.deepcopy(self.accounts)
            previous_allowlist = copy.deepcopy(self.family_email_allowlist)
            role_lbl = "Người nhà (Tầng 2)" if tier_int == 2 else "Khách (Tầng 3)"
            role_str = "MEMBER" if tier_int == 2 else "CHILD_GUEST"
            tier_permissions = (
                [
                    "Bật/Tắt Đèn, Quạt, Máy bơm, Điều hòa",
                    "Không có quyền thêm thành viên hoặc gửi link mời",
                    "Bị chặn Mở Cửa chính (D1) & Còi báo động (D8)",
                ]
                if tier_int == 2
                else [
                    "Chỉ bật/tắt đèn & quạt cơ bản",
                    "Không có quyền thêm thành viên",
                ]
            )
            allow_entry = {
                "email": clean_email,
                "target_tier": tier_int,
                "target_role_label": role_lbl,
                "added_by": actor["email"],
                "added_by_name": actor["display_name"],
                "added_by_tier": actor_tier,
                "added_at": _now_vn(),
            }
            self.family_email_allowlist[clean_email] = allow_entry

            clean_id = re.sub(r"[^a-z0-9_]", "_", clean_email.split("@")[0].lower())
            reading_prompt = build_reading_prompt(clean_email.split("@")[0].replace(".", " ").title(), tier_int)
            acc = self.find_account(clean_email)
            if not acc:
                acc = {
                    "account_id": clean_id,
                    "email": clean_email,
                    "display_name": clean_email.split("@")[0].replace(".", " ").title(),
                    "tier": tier_int,
                    "saved_tier": tier_int,
                    "role": role_str,
                    "role_label": f"{role_lbl} - Thiết bị sinh hoạt" if tier_int == 2 else f"{role_lbl} được cấp quyền",
                    "permission_active": True,
                    "permission_status": "ACTIVE",
                    "permission_label": f"CÓ QUYỀN (Tầng {tier_int})",
                    "password_hash": "",
                    "google_linked": True,
                    "invited_by": f"{actor['display_name']} (Cấp {actor_tier})",
                    "needs_first_page_voice_enroll": True,
                    "voice_verified": False,
                    "reading_prompt": reading_prompt,
                    "voiceprint": {
                        "enrolled": False,
                        "f0_mean_hz": 0.0,
                        "reading_prompt_verified": False,
                        "source_device": "Chờ thu âm giọng chính",
                        "updated_at": _now_vn(),
                    },
                    "permissions": tier_permissions,
                }
                self.accounts.append(acc)
            else:
                acc["tier"] = tier_int
                acc["saved_tier"] = tier_int
                acc["role"] = role_str
                acc["role_label"] = f"{role_lbl} - Thiết bị sinh hoạt" if tier_int == 2 else f"{role_lbl} được cấp quyền"
                acc["permission_active"] = True
                acc["permission_status"] = "ACTIVE"
                acc["permission_label"] = f"CÓ QUYỀN (Tầng {tier_int})"
                acc.pop("revoked_at", None)
                acc.pop("revoked_by", None)
                acc["permissions"] = tier_permissions
                acc["invited_by"] = f"{actor['display_name']} (Cấp {actor_tier})"
                acc["needs_first_page_voice_enroll"] = True
                acc["voice_verified"] = False
                acc["reading_prompt"] = reading_prompt

            if not self._save_accounts():
                self.accounts[:] = previous_accounts
                self.family_email_allowlist = previous_allowlist
                return {
                    "ok": False,
                    "status_code": 503,
                    "error": "Không lưu được danh sách tài khoản. Hãy thử lại sau.",
                }
            self._save_family_allowlist()

            self._log_event(
                layer="Email Allowlist",
                action="family_email_added",
                email=clean_email,
                status="PASS",
                detail=f"{actor['display_name']} (Cấp {actor_tier}) đã thêm email {clean_email} vào {role_lbl}.",
                source=source,
                extra=allow_entry,
            )

            return {
                "ok": True,
                "status_code": 200,
                "target_email": clean_email,
                "target_tier": tier_int,
                "target_role_label": role_lbl,
                "added_by": actor["email"],
                "voice_verified": False,
                "needs_first_page_voice_enroll": True,
                "account": acc,
                "entry": allow_entry,
                "message": f"✅ Đã thêm email {clean_email} vào danh sách Cấp {tier_int} ({role_lbl}) thành công!",
            }

        with_cas = getattr(self, "_with_cas_accounts", None)
        if callable(with_cas):
            return with_cas(_mutate)
        return _mutate()

    def get_family_email_allowlist(self) -> list[dict[str, Any]]:
        """Trả về toàn bộ danh sách Email Gia Đình đã được cấp quyền."""
        return list(self.family_email_allowlist.values())

    def check_duplicate_voice_gate(
        self,
        feat_s1: bytes | Any,
        deep_feat: Any = None,
        threshold_mel: float = THRESHOLD_MEL,
        threshold_deep: float = THRESHOLD_DEEP,
        f0_hz: float | None = None,
        target_tier: int = 0,
        target_user_id: str = "",
    ) -> Any:
        """Cổng Kiểm Tra Chống Trùng Giọng Trong Nhà (ủy quyền trực tiếp tới VoiceAuthManager)."""
        from simulator.voice_auth import VoiceAuthManager
        vm = VoiceAuthManager(ROOT_DIR / "test_audio")
        return vm.check_duplicate_voice_gate(
            feat_s1=feat_s1,
            deep_feat=deep_feat,
            threshold_mel=threshold_mel,
            threshold_deep=threshold_deep,
            f0_hz=f0_hz,
            target_tier=target_tier,
            target_user_id=target_user_id,
        )

    def validate_and_enroll_voice(
        self,
        email: str,
        pcm_bytes: bytes | str,
        source_device: str = "Voice Enrollment (Audio Upload)",
        check_duplicate: bool = True,
        samples_pcm: list[bytes] | None = None,
        self_check_pcm_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Kiểm định chất lượng âm thanh, kiểm tra chống trùng giọng trong nhà và lưu hồ sơ giọng chính (WeSpeaker ResNet34 ONNX + 5-Sample Mean)."""
        from simulator.voice.enrollment_quality import check_enrollment_quality_gate
        from simulator.voice.wespeaker_onnx import (
            compute_multi_sample_mean_embedding,
            extract_wespeaker_embedding,
        )
        from simulator.voice_auth import validate_voice_enrollment_quality
        from simulator.voice_config import get_tier_wespeaker_threshold

        clean_email = email.strip().lower()
        acc = self.find_account(clean_email)
        if not acc:
            return {
                "ok": False,
                "status": "CHUA_DAT",
                "status_code": 400,
                "message": f"Không tìm thấy tài khoản '{email}'!",
                "error": f"Không tìm thấy tài khoản '{email}'!",
            }

        if isinstance(pcm_bytes, str):
            try:
                pcm_data = base64.b64decode(pcm_bytes)
            except Exception:
                pcm_data = pcm_bytes.encode("utf-8")
        else:
            pcm_data = bytes(pcm_bytes)

        strict_gate = check_enrollment_quality_gate(
            enroll_pcm=pcm_data if pcm_data else b"".join(samples_pcm or []),
            self_check_pcm=self_check_pcm_bytes,
            sr=16000,
            require_self_check=True,
        )
        if not strict_gate.get("ok"):
            return {
                **strict_gate,
                "ok": False,
                "status": "CHUA_DAT",
                "status_code": 400,
                "error": strict_gate.get("message") or "Mẫu giọng đăng ký chưa đạt chuẩn chất lượng.",
            }

        val_res = validate_voice_enrollment_quality(pcm_data, sr=16000)

        if not val_res.get("ok"):
            if not acc.get("voice_verified", False):
                acc["voice_verified"] = False
                acc["needs_first_page_voice_enroll"] = True
                self._save_accounts()
            self._log_event(
                layer="Thu Âm Giọng Chính",
                action="voice_enroll_failed",
                email=clean_email,
                status="FAIL",
                detail=f"Kiểm định giọng {clean_email} CHƯA ĐẠT: {val_res.get('reason', '')}",
                source=source_device,
                extra=val_res.get("details", {}),
            )
            return {
                "ok": False,
                "status": "CHUA_DAT",
                "ask_repeat": True,
                "message": "Giọng thu âm chưa đạt chuẩn (Chưa được)",
                "reason": val_res.get("reason", "Chất lượng âm thanh chưa đạt chuẩn"),
                "details": val_res.get("details", {}),
            }

        acc_tier = int(acc.get("tier", 2))
        acc_uid = str(acc.get("account_id", ""))
        samples_count = 1
        if samples_pcm and len(samples_pcm) >= 2:
            multi_res = compute_multi_sample_mean_embedding(
                samples_pcm,
                sr=16000,
                required_samples=len(samples_pcm),
                enforce_distinct=True,
            )
            if not multi_res.get("ok"):
                return {
                    "ok": False,
                    "status": "CHUA_DAT",
                    "ask_repeat": bool(multi_res.get("ask_repeat", False)),
                    "reason": multi_res.get("reason", "MULTI_SAMPLE_FAILED"),
                    "message": multi_res.get("message", "Các mẫu giọng thu âm chưa đạt chuẩn."),
                    "error": multi_res.get("message", "Các mẫu giọng thu âm chưa đạt chuẩn."),
                }
            wespk_vec = multi_res.get("wespeaker_embedding", [])
            samples_count = int(multi_res.get("num_samples", len(samples_pcm)))
        else:
            wespk_vec = [
                round(float(v), 6)
                for v in extract_wespeaker_embedding(pcm_data).tolist()
            ]

        if check_duplicate:
            dup_res = self.check_duplicate_voice_gate(
                {
                    "embedding": val_res.get("embedding", []),
                    "f0_hz": val_res.get("f0_hz", 126.0),
                    "wespeaker_embedding": wespk_vec,
                    "embedding_256d": wespk_vec,
                },
                deep_feat={"deep_embedding": val_res.get("deep_embedding", [])},
                f0_hz=float(val_res.get("f0_hz", 126.0)),
                target_tier=acc_tier,
                target_user_id=acc_uid,
            )
            if dup_res.is_duplicate:
                if not acc.get("voice_verified", False):
                    acc["voice_verified"] = False
                    acc["needs_first_page_voice_enroll"] = True
                    self._save_accounts()
                self._log_event(
                    layer="Thu Âm Giọng Chính",
                    action="voice_enroll_duplicate_rejected",
                    email=clean_email,
                    status="FAIL",
                    detail=f"Từ chối thu âm {clean_email}: Trùng giọng với {dup_res.matched_name} (Cấp {dup_res.matched_tier})!",
                    source=source_device,
                )
                return {
                    "ok": False,
                    "duplicate_blocked": True,
                    "status": "DUPLICATE_VOICE_REJECTED",
                    "reason": dup_res.reason,
                    "message": dup_res.message,
                    "error": dup_res.message,
                    "matched_tier": dup_res.matched_tier,
                    "matched_name": dup_res.matched_name,
                }

        prev_accounts = copy.deepcopy(self.accounts)
        f0_val = float(val_res.get("f0_hz", 126.0))
        tier_thr = get_tier_wespeaker_threshold(acc_tier)
        acc["voice_verified"] = True
        acc["needs_first_page_voice_enroll"] = False
        acc["voiceprint"] = {
            "enrolled": True,
            "wespeaker_model": "wespeaker_r34_onnx",
            "threshold_wespeaker": tier_thr,
            "enrollment_samples_count": samples_count,
            "wespeaker_embedding": wespk_vec,
            "embedding_256d": wespk_vec,
            "f0_mean_hz": f0_val,
            "f0_min_hz": round(max(75.0, f0_val - 20.0), 1),
            "f0_max_hz": round(min(340.0, f0_val + 20.0), 1),
            "centroid_hz": float(val_res.get("centroid_hz", f0_val * 9.5)),
            "reading_prompt_verified": True,
            "source_device": source_device,
            "updated_at": _now_vn(),
            "embedding": val_res.get("embedding", []),
            "deep_embedding": val_res.get("deep_embedding", []),
        }
        if not self._save_accounts():
            self.accounts[:] = prev_accounts
            err_persist = "Lỗi lưu trữ bền vững đám mây (Durable Store). Đã hoàn tác đăng ký giọng nói!"
            return {
                "ok": False,
                "status": "DURABLE_PERSISTENCE_FAILED",
                "status_code": 503,
                "reason": "DURABLE_PERSISTENCE_FAILED",
                "error": err_persist,
                "message": err_persist,
            }

        self._log_event(
            layer="Thu Âm Giọng Chính",
            action="voice_enroll_passed",
            email=clean_email,
            status="PASS",
            detail=(
                f"Kiểm định giọng {clean_email} ĐÃ ĐẠT (WeSpeaker ResNet34 ONNX, {samples_count} mẫu, "
                f"ngưỡng={tier_thr}): F0={f0_val}Hz. Đã lưu hồ sơ giọng chính!"
            ),
            source=source_device,
            extra={"f0_hz": f0_val, "duration_sec": val_res.get("duration_sec"), "samples_count": samples_count},
        )

        return {
            "ok": True,
            "status": "DA_DAT",
            "message": "Giọng chính đã đạt chuẩn (Đã được)",
            "f0_hz": f0_val,
            "sample_count": samples_count,
            "enrollment_samples_count": samples_count,
            "threshold_wespeaker": tier_thr,
            "account": acc,
            "voiceprint": acc["voiceprint"],
        }

    def get_invite_links_for_account(self, issuer_identifier: str) -> dict[str, Any]:
        """Trả về các đường link mời mà tài khoản hiện tại được phép gửi xuống cấp dưới."""
        acc = self.find_account(issuer_identifier)
        if not acc:
            return {
                "ok": False,
                "can_invite": False,
                "allowed_target_tiers": [],
                "links": [],
                "error": f"Không tìm thấy tài khoản '{issuer_identifier}'!",
            }

        if not acc.get("permission_active", True):
            return {
                "ok": False,
                "can_invite": False,
                "issuer": acc["display_name"],
                "issuer_tier": acc["tier"],
                "permission_status": "REVOKED",
                "allowed_target_tiers": [],
                "links": [],
                "error": f"🚫 Tài khoản {acc['display_name']} hiện KHÔNG CÓ QUYỀN (Đã bị Chủ nhà tạm thu hồi quyền) nên không thể gửi link mời!",
            }

        tier = int(acc["tier"])
        if tier == 1:
            links = [
                self.invite_links.get("INV-T1-TO-TIER2", DEFAULT_INVITE_LINKS["INV-T1-TO-TIER2"]),
                self.invite_links.get("INV-T1-TO-TIER3", DEFAULT_INVITE_LINKS["INV-T1-TO-TIER3"]),
            ]
            return {
                "ok": True,
                "can_invite": True,
                "issuer": acc["display_name"],
                "issuer_email": acc["email"],
                "issuer_tier": 1,
                "allowed_target_tiers": [2, 3],
                "rule_explanation": "Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền mời thành viên Cấp 2 (Người nhà) và Cấp 3 (Khách).",
                "links": links,
            }
        return {
            "ok": True,
            "can_invite": False,
            "rbac_blocked": True,
            "issuer": acc["display_name"],
            "issuer_email": acc["email"],
            "issuer_tier": tier,
            "allowed_target_tiers": [],
            "rule_explanation": "Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền tạo và gửi đường link mời.",
            "links": [],
        }

    def create_custom_invite_link(
        self,
        issuer_identifier: str,
        target_tier: int,
        source: str = "Web/App",
    ) -> dict[str, Any]:
        """Kiểm tra chặt chẽ phân quyền tạo link mời (Chỉ Chủ nhà Cấp 1 mới có quyền)."""
        acc = self.find_account(issuer_identifier)
        if not acc:
            return {
                "ok": False,
                "status_code": 404,
                "error": f"Không tìm thấy người tạo link '{issuer_identifier}'.",
            }

        if not acc.get("permission_active", True):
            msg = f"🚫 Tài khoản {acc['display_name']} đang ở trạng thái KHÔNG CÓ QUYỀN (Đã bị Chủ nhà thu hồi quyền)!"
            self._log_event(
                layer="Phân cấp Link Mời",
                action="invite_blocked_revoked",
                email=acc["email"],
                status="FAIL",
                detail=msg,
                source=source,
            )
            return {"ok": False, "status_code": 403, "rbac_blocked": True, "error": msg}

        issuer_tier = int(acc["tier"])
        target_tier = int(target_tier)

        if issuer_tier != 1:
            msg = (
                f"🚫 Từ chối: Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền tạo hoặc gửi link mời! "
                f"Tài khoản Cấp {issuer_tier} ({acc['display_name']}) không có quyền mời."
            )
            self._log_event(
                layer="Phân cấp Link Mời",
                action=f"tier{issuer_tier}_invite_blocked",
                email=acc["email"],
                status="FAIL",
                detail=msg,
                source=source,
            )
            return {
                "ok": False,
                "status_code": 403,
                "rbac_blocked": True,
                "error": msg,
            }

        if target_tier not in (2, 3):
            msg = "Cấp 1 chỉ tạo đường link mời xuống Cấp 2 hoặc Cấp 3."
            return {"ok": False, "status_code": 400, "error": msg}

        code = f"INV-T{issuer_tier}-TO-TIER{target_tier}"
        role_lbl = "Người nhà (Tầng 2)" if target_tier == 2 else "Khách (Tầng 3)"
        link_obj = {
            "invite_code": code,
            "issuer_email": acc["email"],
            "issuer_name": f"{acc['display_name']} (Cấp {issuer_tier})",
            "issuer_tier": issuer_tier,
            "target_tier": target_tier,
            "target_role_label": role_lbl,
            "url_path": f"/auth?invite={code}",
            "full_url": f"http://localhost:8088/auth?invite={code}",
            "description": f"Link do {acc['display_name']} (Cấp {issuer_tier}) gửi xuống để đăng ký Cấp {target_tier}",
            "created_at": _now_vn(),
        }
        self.invite_links[code] = link_obj
        self._save_invite_links()
        self._log_event(
            layer="Phân cấp Link Mời",
            action="invite_link_created",
            email=acc["email"],
            status="PASS",
            detail=f"{acc['display_name']} (Cấp {issuer_tier}) đã xuất link mời Cấp {target_tier}: {link_obj['full_url']}",
            source=source,
            extra=link_obj,
        )
        return {
            "ok": True,
            "status_code": 200,
            "invite_link": link_obj,
            "message": f"✅ Đã tạo đường link mời Cấp {target_tier}: {link_obj['full_url']}",
        }

    def send_invite_link_via_gmail(
        self,
        invite_code: str,
        recipient_email: str,
        source: str = "Web Portal",
    ) -> dict[str, Any]:
        """Gửi trực tiếp đường Link Mời đăng ký xuống Gmail của người cấp dưới qua `gws gmail`."""
        code = (invite_code or "").strip().upper()
        if code == "INV-T2-TO-TIER3":
            msg = "🚫 Đường link mời Cấp 2 (INV-T2-TO-TIER3) đã bị vô hiệu hóa. Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền gửi lời mời!"
            if hasattr(self, "_log_event"):
                self._log_event(
                    layer="Phân cấp Link Mời",
                    action="tier2_invite_email_blocked",
                    email=(recipient_email or "").strip().lower(),
                    status="FAIL",
                    detail=msg,
                    source=source,
                )
            return {
                "ok": False,
                "status_code": 403,
                "rbac_blocked": True,
                "sent_real_gmail": False,
                "error": msg,
            }

        inv = self.invite_links.get(code) or DEFAULT_INVITE_LINKS.get(code)
        if inv and int(inv.get("issuer_tier", 1)) != 1:
            msg = "🚫 Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền phát hành và gửi đường link mời!"
            return {
                "ok": False,
                "status_code": 403,
                "rbac_blocked": True,
                "sent_real_gmail": False,
                "error": msg,
            }

        raw_recipient = recipient_email if isinstance(recipient_email, str) else ""
        to_addr = strict_single_email_ascii(raw_recipient) or raw_recipient.strip().lower()
        if not is_email_allowlisted_for_real_send(raw_recipient):
            if hasattr(self, "_log_event"):
                self._log_event(
                    layer="Email Allowlist Protection Gate",
                    action="blocked_non_allowlisted_invite_email",
                    email=to_addr,
                    status="BLOCKED",
                    detail=f"Chặn gửi đường link mời tới '{to_addr}' vì không thuộc REAL_EMAIL_ALLOWLIST (Chống bounce mail).",
                    source=source,
                )
            return {
                "ok": False,
                "status_code": 403,
                "sent_real_gmail": False,
                "blocked_by_allowlist": True,
                "recipient": to_addr,
                "status": "BLOCKED_NOT_ALLOWLISTED",
                "error": f"Email '{to_addr}' không nằm trong REAL_EMAIL_ALLOWLIST! Chặn gửi an toàn.",
                "message": f"Chặn gửi thư mời an toàn: '{to_addr}' không nằm trong REAL_EMAIL_ALLOWLIST.",
            }

        if not inv:
            return {
                "ok": False,
                "status_code": 404,
                "sent_real_gmail": False,
                "error": f"Không tìm thấy đường link mời '{invite_code}'!",
            }

        sender_name = "Smart Home Voice AI"
        sender_addr = os.environ.get("SMTP_USER", "").strip() or "nep94121@gmail.com"
        domain = sender_addr.split("@")[-1] if "@" in sender_addr else "gmail.com"
        to_name = to_addr.split("@")[0]

        msg = MIMEMultipart("alternative")
        msg["From"] = email.utils.formataddr((sender_name, sender_addr))
        msg["To"] = email.utils.formataddr((to_name, to_addr))
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain=domain)
        msg["Reply-To"] = email.utils.formataddr((sender_name, sender_addr))
        msg["Subject"] = f"Smart Home Voice - Lời mời đăng ký tài khoản Cấp {inv['target_tier']} ({inv['target_role_label']})"

        plain_body = (
            f"Xin chào,\n\n"
            f"Bạn vừa nhận được lời mời tham gia hệ thống Smart Home Voice từ {inv['issuer_name']}.\n"
            f"Cấp quyền: Tầng {inv['target_tier']} ({inv['target_role_label']})\n"
            f"Đường link đăng ký: {inv['full_url']}\n\n"
            f"Hướng dẫn: Mở đường link trên, chọn Đăng nhập bằng Gmail để nhận mã xác thực và hoàn tất đăng ký.\n"
            f"Sau khi vào Trang Đầu, hãy đọc câu mẫu để hệ thống lưu giọng nói mẫu.\n\n"
            f"Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói Tiếng Việt (ĐATN SEEE - HUST)."
        )

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;margin:0;padding:24px;background-color:#f8fafc;color:#1e293b;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:540px;background-color:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,0.05);" border="0" cellspacing="0" cellpadding="0">
          <tr>
            <td>
              <h2 style="color:#0f172a;font-size:20px;font-weight:700;margin:0 0 4px 0;">Smart Home Voice</h2>
              <div style="color:#64748b;font-size:14px;margin-bottom:20px;">Lời mời đăng ký tài khoản thành viên</div>
              
              <p style="font-size:14px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Xin chào,</p>
              <p style="font-size:14px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Bạn vừa nhận được đường link mời đăng ký tài khoản <b>Cấp {inv['target_tier']} ({inv['target_role_label']})</b> từ <b>{inv['issuer_name']}</b> trên hệ thống Smart Home Voice.</p>
              
              <div style="background-color:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:20px;text-align:center;margin:24px 0;">
                <div style="font-size:13px;color:#166534;margin-bottom:12px;">Nhấn vào liên kết bên dưới để kích hoạt tài khoản:</div>
                <a href="{inv['full_url']}" style="display:inline-block;background-color:#16a34a;color:#ffffff;font-weight:600;padding:12px 24px;border-radius:6px;text-decoration:none;font-size:14px;">Đăng ký tài khoản Cấp {inv['target_tier']}</a>
                <div style="margin-top:12px;font-size:12px;color:#64748b;">Hoặc sao chép liên kết: <code style="color:#0f172a;">{inv['full_url']}</code></div>
              </div>
              
              <p style="font-size:12px;line-height:1.5;color:#64748b;margin:0 0 8px 0;">• Khi mở liên kết, hãy chọn Đăng nhập bằng Gmail để nhận mã xác thực.<br>• Sau đó vào Trang Đầu đọc dòng chữ mẫu để lưu giọng nói gốc lên hệ thống.</p>
              <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0 16px 0;">
              <div style="font-size:11px;color:#94a3b8;text-align:center;">Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói Tiếng Việt (ĐATN SEEE - HUST)</div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        raw_b64 = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        try:
            proc = subprocess.run(
                [
                    "gws",
                    "gmail",
                    "users",
                    "messages",
                    "send",
                    "--params",
                    json.dumps({"userId": "me"}),
                    "--json",
                    json.dumps({"raw": raw_b64}),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                shell=True,
            )
            if proc.returncode == 0 and '"id"' in proc.stdout:
                out_obj = json.loads(proc.stdout[proc.stdout.find("{") :])
                msg_id = out_obj.get("id", "")
                self._log_event(
                    layer="Gửi Link Mời Qua Gmail",
                    action="invite_email_sent",
                    email=to_addr,
                    status="PASS",
                    detail=f"Đã gửi đường link mời {inv['full_url']} tới Gmail {to_addr} (MsgID: {msg_id}).",
                    source=source,
                )
                return {
                    "ok": True,
                    "sent_real_gmail": True,
                    "blocked_by_allowlist": False,
                    "recipient": to_addr,
                    "invite_url": inv["full_url"],
                    "gmail_message_id": msg_id,
                    "message": f"✅ Đã gửi đường link mời Cấp {inv['target_tier']} tới hộp thư Gmail: {to_addr}!",
                }
            return {
                "ok": False,
                "sent_real_gmail": False,
                "blocked_by_allowlist": False,
                "recipient": to_addr,
                "error": (proc.stderr or proc.stdout or "Lỗi gửi Gmail")[:200],
            }
        except Exception as exc:
            return {
                "ok": False,
                "sent_real_gmail": False,
                "blocked_by_allowlist": False,
                "recipient": to_addr,
                "error": str(exc)[:200],
            }

    def send_real_gmail_otp(
        self,
        target_email: str,
        otp_code: str,
        display_name: str,
        issued_password: str = "",
        invite_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw_recipient = target_email if isinstance(target_email, str) else ""
        recipient = strict_single_email_ascii(raw_recipient) or raw_recipient.strip().lower()
        if not is_email_allowlisted_for_real_send(raw_recipient):
            if hasattr(self, "_log_event"):
                self._log_event(
                    layer="Email Allowlist Protection Gate",
                    action="blocked_non_allowlisted_email",
                    email=recipient,
                    status="BLOCKED",
                    detail=f"Chặn gửi thư thật tới '{recipient}' vì không thuộc REAL_EMAIL_ALLOWLIST (Chống bounce mail).",
                    source="EmailProtectionGate",
                )
            return {
                "sent_real_gmail": False,
                "blocked_by_allowlist": True,
                "actual_recipient": recipient,
                "status": "BLOCKED_NOT_ALLOWLISTED",
                "message": f"Địa chỉ '{recipient}' không thuộc danh sách REAL_EMAIL_ALLOWLIST. Chặn gửi an toàn.",
            }

        actual_to = recipient

        sender_name = "Smart Home Voice AI"
        smtp_user = os.environ.get("SMTP_USER", "").strip() or "nep94121@gmail.com"
        domain = smtp_user.split("@")[-1] if "@" in smtp_user else "gmail.com"
        to_name = display_name or actual_to.split("@")[0]

        msg = MIMEMultipart("alternative")
        msg["From"] = email.utils.formataddr((sender_name, smtp_user))
        msg["To"] = email.utils.formataddr((to_name, actual_to))
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain=domain)
        msg["Reply-To"] = email.utils.formataddr((sender_name, smtp_user))
        msg["Subject"] = "Smart Home Voice - Mã xác thực tài khoản"

        if invite_info or issued_password:
            inv_by = (invite_info or {}).get("issuer_name", "Chủ nhà")
            t_tier = (invite_info or {}).get("target_tier", 2)
            plain_text = (
                f"Xin chào {display_name},\n\n"
                f"Bạn vừa nhận được lời mời tham gia hệ thống Smart Home Voice từ {inv_by}.\n"
                f"Cấp quyền: Tầng {t_tier}\n"
                f"Mật khẩu cấp phát: {issued_password}\n\n"
                f"Mã xác thực của bạn là: {otp_code}\n"
                f"Mã có hiệu lực trong vòng 5 phút.\n\n"
                f"Lưu ý: Sau khi xác thực, hãy vào Trang Đầu đọc câu mẫu để hệ thống lưu giọng nói mẫu.\n\n"
                f"Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói Tiếng Việt (ĐATN SEEE - HUST)."
            )
            extra_invite_html = f"""
            <div style="background-color:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:14px;margin:16px 0;font-size:13px;color:#0369a1;">
              <div><b>Người mời:</b> {inv_by}</div>
              <div style="margin-top:4px;"><b>Cấp quyền được gán:</b> Tầng {t_tier}</div>
              <div style="margin-top:4px;"><b>Mật khẩu tài khoản:</b> <code style="color:#0284c7;font-weight:bold;font-size:14px;">{issued_password}</code></div>
              <div style="margin-top:8px;font-size:12px;color:#0c4a6e;"><i>Lưu ý: Sau khi xác thực tài khoản và vào Trang Đầu, hãy đọc câu mẫu để lưu giọng nói chủ trên máy chủ.</i></div>
            </div>
            """
        else:
            plain_text = (
                f"Xin chào {display_name},\n\n"
                f"Mã xác thực Smart Home Voice của bạn là: {otp_code}\n"
                f"Mã có hiệu lực trong vòng 5 phút.\n"
                f"Vui lòng không chia sẻ mã này cho bất kỳ ai để bảo mật tài khoản.\n\n"
                f"Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói Tiếng Việt (ĐATN SEEE - HUST)."
            )
            extra_invite_html = ""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;margin:0;padding:24px;background-color:#f8fafc;color:#1e293b;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:540px;background-color:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,0.05);" border="0" cellspacing="0" cellpadding="0">
          <tr>
            <td>
              <h2 style="color:#0f172a;font-size:20px;font-weight:700;margin:0 0 4px 0;">Smart Home Voice</h2>
              <div style="color:#64748b;font-size:14px;margin-bottom:20px;">Xác thực tài khoản người dùng</div>
              
              <p style="font-size:14px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Xin chào <b>{display_name}</b>,</p>
              <p style="font-size:14px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Bạn vừa yêu cầu mã xác thực cho tài khoản <code>{recipient}</code> trên hệ thống Smart Home Voice. Vui lòng sử dụng mã bên dưới:</p>
              
              {extra_invite_html}
              
              <div style="background-color:#f1f5f9;border:1px solid #cbd5e1;border-radius:8px;padding:20px;text-align:center;margin:24px 0;">
                <div style="font-size:12px;font-weight:600;letter-spacing:1px;color:#64748b;text-transform:uppercase;">Mã xác thực của bạn</div>
                <div id="otp-code-value" style="font-size:32px;font-weight:700;letter-spacing:6px;color:#0f172a;margin-top:8px;">{otp_code}</div>
              </div>
              
              <p style="font-size:12px;line-height:1.5;color:#64748b;margin:0 0 8px 0;">• Mã có hiệu lực trong vòng 5 phút.<br>• Vui lòng không tiết lộ mã xác thực này cho người khác để bảo vệ an toàn cho ngôi nhà của bạn.</p>
              <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0 16px 0;">
              <div style="font-size:11px;color:#94a3b8;text-align:center;">Hệ thống Nhà Thông Minh Điều Khiển Bằng Giọng Nói Tiếng Việt (ĐATN SEEE - HUST)</div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # 1. Thử gửi qua SMTP nếu có GMAIL_APP_PASSWORD hoặc SMTP_PASSWORD
        smtp_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip() or os.environ.get("SMTP_PASSWORD", "").strip()
        if smtp_pass:
            smtp_host = os.environ.get("SMTP_HOST", "").strip() or "smtp.gmail.com"
            port_val = os.environ.get("SMTP_PORT", "").strip() or "587"
            try:
                smtp_port = int(port_val)
            except ValueError:
                smtp_port = 587

            try:
                if smtp_port == 465:
                    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as server:
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(smtp_host, smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                return {
                    "sent_real_gmail": True,
                    "blocked_by_allowlist": False,
                    "actual_recipient": actual_to,
                    "method": "smtp",
                    "smtp_host": smtp_host,
                }
            except Exception as exc:
                return {
                    "sent_real_gmail": False,
                    "blocked_by_allowlist": False,
                    "actual_recipient": actual_to,
                    "error": f"Lỗi gửi email qua SMTP: {str(exc)[:150]}",
                    "note": str(exc)[:200],
                }

        # 2. Fallback: Thử qua CLI `gws` nếu có
        raw_b64 = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        try:
            body_json = json.dumps({"raw": raw_b64})
            params_json = json.dumps({"userId": "me"})
            proc = subprocess.run(
                [
                    "gws",
                    "gmail",
                    "users",
                    "messages",
                    "send",
                    "--params",
                    params_json,
                    "--json",
                    body_json,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                shell=True,
            )
            if proc.returncode == 0 and '"id"' in proc.stdout:
                out_obj = json.loads(proc.stdout[proc.stdout.find("{") :])
                return {
                    "sent_real_gmail": True,
                    "blocked_by_allowlist": False,
                    "actual_recipient": actual_to,
                    "method": "gws",
                    "gmail_message_id": out_obj.get("id", ""),
                }
        except Exception:
            pass

        # 3. Không có cả SMTP secret lẫn gws -> Báo lỗi thiếu secret rõ ràng
        return {
            "sent_real_gmail": False,
            "blocked_by_allowlist": False,
            "actual_recipient": actual_to,
            "missing_secret": "GMAIL_APP_PASSWORD",
            "error": "Thiếu biến môi trường cấu hình mật khẩu ứng dụng Gmail ('GMAIL_APP_PASSWORD' hoặc 'SMTP_PASSWORD').",
            "note": "Không tìm thấy GMAIL_APP_PASSWORD/SMTP_PASSWORD và không có gws CLI trên môi trường hiện tại.",
        }

    def read_latest_otp_from_gmail_inbox(self, message_id: str = "") -> dict[str, Any]:
        """Tự động vào hộp thư Gmail thật (`nep94121@gmail.com`) qua `gws gmail` để đọc thư vừa gửi và trích xuất mã OTP 6 số."""
        try:
            target_id = message_id.strip()
            if not target_id:
                list_params = json.dumps({
                    "userId": "me",
                    "maxResults": 5,
                    "q": 'subject:"Smart Home" (xác thực OR OTP OR verification)',
                })
                proc_list = subprocess.run(
                    ["gws", "gmail", "users", "messages", "list", "--params", list_params],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=12,
                    shell=True,
                )
                if proc_list.returncode == 0 and '"messages"' in proc_list.stdout:
                    obj_l = json.loads(proc_list.stdout[proc_list.stdout.find("{") :])
                    msgs = obj_l.get("messages", [])
                    if msgs:
                        target_id = msgs[0].get("id", "")

            if not target_id:
                return {"ok": False, "error": "Không tìm thấy message_id trong hộp thư Gmail."}

            get_params = json.dumps({"userId": "me", "id": target_id, "format": "full"})
            proc_get = subprocess.run(
                ["gws", "gmail", "users", "messages", "get", "--params", get_params],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=12,
                shell=True,
            )
            if proc_get.returncode != 0 or "{" not in proc_get.stdout:
                return {"ok": False, "error": (proc_get.stderr or proc_get.stdout)[:200]}

            msg_obj = json.loads(proc_get.stdout[proc_get.stdout.find("{") :])
            snippet = str(msg_obj.get("snippet", ""))
            headers = msg_obj.get("payload", {}).get("headers", [])
            subject = ""
            for h in headers:
                if str(h.get("name", "")).lower() == "subject":
                    subject = str(h.get("value", ""))
                    break

            def _extract_payload_text(payload_dict: dict[str, Any]) -> str:
                texts: list[str] = []

                def _walk(part: dict[str, Any]):
                    data = part.get("body", {}).get("data", "")
                    if data:
                        try:
                            pad = len(data) % 4
                            padded_data = data + ("=" * (4 - pad) if pad else "")
                            decoded = base64.urlsafe_b64decode(padded_data.encode("ascii")).decode("utf-8", errors="replace")
                            texts.append(decoded)
                        except Exception:
                            pass
                    for sub_part in part.get("parts", []):
                        _walk(sub_part)

                _walk(payload_dict)
                return "\n".join(texts)

            payload_text = _extract_payload_text(msg_obj.get("payload", {}))
            full_search_text = f"{subject}\n{snippet}\n{payload_text}"

            # 1) Keyword context regex
            m = re.search(r"(?:OTP[:\s-]*|mã[:\s-]*|code[:\s-]*|xác thực[:\s-]*|xác nhận[:\s-]*)\s*(\d{6})\b", full_search_text, re.IGNORECASE)

            # 2) HTML container regex
            if not m:
                m = re.search(r'id=["\']otp-code-value["\'][^>]*>(?:OTP:)?\s*(\d{6})<', full_search_text, re.IGNORECASE)

            # 3) Fallback boundary regex
            if not m:
                m = re.search(r"\b(\d{6})\b", full_search_text)

            if m:
                extracted_otp = m.group(1)
                return {
                    "ok": True,
                    "gmail_message_id": target_id,
                    "subject": subject,
                    "snippet": snippet,
                    "extracted_otp": extracted_otp,
                }
            return {
                "ok": False,
                "gmail_message_id": target_id,
                "subject": subject,
                "snippet": snippet,
                "error": "Đã đọc thư Gmail nhưng không tìm thấy chuỗi 6 số OTP.",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    def start_invite_oauth_registration(
        self,
        invite_code: str,
        google_email: str,
        display_name: str,
        custom_password: str = "",
        send_gmail: bool = True,
        source: str = "Web Invite Link",
    ) -> dict[str, Any]:
        """Khi cấp dưới bấm vào đường link mời (`/auth?invite=...`) và chọn Đăng nhập bằng Google OAuth (Gmail)."""
        code = (invite_code or "").strip().upper()
        if code == "INV-T2-TO-TIER3":
            msg = "🚫 Mã đường link mời Cấp 2 (INV-T2-TO-TIER3) đã bị vô hiệu hóa. Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền mời thành viên!"
            if hasattr(self, "_log_event"):
                self._log_event(
                    layer="Link Mời + Google OAuth",
                    action="tier2_invite_oauth_blocked",
                    email=(google_email or "").strip().lower(),
                    status="FAIL",
                    detail=msg,
                    source=source,
                )
            return {
                "ok": False,
                "status_code": 403,
                "rbac_blocked": True,
                "error": msg,
            }

        inv = self.invite_links.get(code) or DEFAULT_INVITE_LINKS.get(code)
        if not inv:
            return {
                "ok": False,
                "status_code": 404,
                "error": f"Mã đường link mời '{invite_code}' không tồn tại hoặc không hợp lệ!",
            }

        if int(inv.get("issuer_tier", 1)) != 1:
            return {
                "ok": False,
                "status_code": 403,
                "rbac_blocked": True,
                "error": "Chỉ đường link mời do Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) phát hành mới hợp lệ!",
            }

        target_tier = int(inv["target_tier"])
        clean_email = google_email.strip().lower()
        if not clean_email or "@" not in clean_email:
            return {"ok": False, "status_code": 400, "error": "Vui lòng nhập hoặc chọn địa chỉ Gmail hợp lệ!"}

        issued_password = custom_password.strip() or secrets.token_urlsafe(10)
        otp_code = f"{random.randint(100000, 999999)}"
        name_clean = display_name.strip() or clean_email.split("@")[0].replace(".", " ").title()

        is_allowed = is_email_allowlisted_for_real_send(google_email)
        gmail_res = {"sent_real_gmail": False, "actual_recipient": clean_email, "blocked_by_allowlist": not is_allowed}
        if send_gmail:
            if is_allowed:
                gmail_res = self.send_real_gmail_otp(
                    target_email=clean_email,
                    otp_code=otp_code,
                    display_name=name_clean,
                    issued_password=issued_password,
                    invite_info=inv,
                )
            else:
                if hasattr(self, "_log_event"):
                    self._log_event(
                        layer="Email Allowlist Protection Gate",
                        action="blocked_non_allowlisted_email",
                        email=clean_email,
                        status="BLOCKED",
                        detail=f"Chặn gửi thư thật tới '{clean_email}' vì không thuộc REAL_EMAIL_ALLOWLIST (Chống bounce mail).",
                        source="EmailProtectionGate",
                    )
                gmail_res = {
                    "sent_real_gmail": False,
                    "blocked_by_allowlist": True,
                    "actual_recipient": clean_email,
                    "status": "BLOCKED_NOT_ALLOWLISTED",
                    "message": f"Địa chỉ '{clean_email}' không thuộc danh sách REAL_EMAIL_ALLOWLIST. Chặn gửi an toàn.",
                }

        self.pending_invite_registrations[clean_email] = {
            "invite_code": code,
            "issuer_name": inv["issuer_name"],
            "issuer_tier": inv["issuer_tier"],
            "target_tier": target_tier,
            "email": clean_email,
            "display_name": name_clean,
            "issued_password": issued_password,
            "otp_code": otp_code,
            "gmail_delivery": gmail_res,
            "created_at": time.time(),
            "expires_at": time.time() + 600,
        }

        self._log_event(
            layer="Link Mời + Google OAuth",
            action="invite_oauth_otp_sent",
            email=clean_email,
            status="PASS",
            detail=(
                f"Đăng ký qua link {code} (Cấp {target_tier} do {inv['issuer_name']} mời). "
                f"Đã gửi OTP & mật khẩu cấp phát về Gmail ({gmail_res.get('actual_recipient')})."
            ),
            source=source,
            extra={"invite_code": code, "target_tier": target_tier, "gmail_delivery": gmail_res},
        )

        return {
            "ok": True,
            "invite_code": code,
            "target_tier": target_tier,
            "invited_by": inv["issuer_name"],
            "email": clean_email,
            "display_name": name_clean,
            "issued_password_for_test": issued_password,
            "otp_code_for_test": otp_code,
            "gmail_delivery": gmail_res,
            "message": (
                f"✅ Đã kết nối Google OAuth ({clean_email}) qua link mời Cấp {target_tier}! "
                f"Mã OTP 6 số và mật khẩu đã được gửi về Gmail ({gmail_res.get('actual_recipient')})."
            ),
        }

    def verify_invite_otp_and_create_account(
        self,
        email: str,
        otp_input: str,
        source: str = "Web Invite Link",
    ) -> dict[str, Any]:
        """Xác nhận mã OTP gửi về Gmail khi đăng ký qua Link mời -> Kích hoạt tài khoản."""
        clean_email = email.strip().lower()
        pend = self.pending_invite_registrations.get(clean_email)
        if not pend:
            return {"ok": False, "error": f"Không tìm thấy hồ sơ đăng ký chờ xác nhận OTP cho '{email}'!"}

        if otp_input.strip() != pend["otp_code"]:
            self._log_event(
                layer="Link Mời + Gmail OTP",
                action="invite_otp_failed",
                email=clean_email,
                status="FAIL",
                detail="Nhập sai OTP đăng ký link mời: mã OTP không khớp.",
                source=source,
            )
            return {
                "ok": False,
                "error": f"Mã OTP '{otp_input}' không đúng!",
            }

        target_tier = int(pend["target_tier"])
        role_str = "MEMBER" if target_tier == 2 else "CHILD_GUEST"
        role_lbl = "Người nhà (Tầng 2 - Thiết bị sinh hoạt)" if target_tier == 2 else "Khách được cấp quyền (Tầng 3)"
        reading_prompt = build_reading_prompt(pend["display_name"], target_tier)
        issued_pw = str(pend.get("issued_password") or "").strip() or secrets.token_urlsafe(10)

        acc = self.find_account(clean_email)
        clean_id = re.sub(r"[^a-z0-9_]", "_", clean_email.split("@")[0].lower())
        if not acc:
            acc = {
                "account_id": clean_id,
                "email": clean_email,
                "display_name": pend["display_name"],
                "tier": target_tier,
                "saved_tier": target_tier,
                "role": role_str,
                "role_label": role_lbl,
                "permission_active": True,
                "permission_status": "ACTIVE",
                "permission_label": f"CÓ QUYỀN (Tầng {target_tier})",
                "password_hash": hash_password(issued_pw),
                "google_linked": True,
                "invited_by": pend["issuer_name"],
                "needs_first_page_voice_enroll": True,
                "reading_prompt": reading_prompt,
                "voiceprint": {
                    "enrolled": False,
                    "f0_mean_hz": 0.0,
                    "reading_prompt_verified": False,
                    "source_device": "Chờ thu âm trang đầu",
                    "updated_at": _now_vn(),
                },
                "permissions": (
                    [
                        "Bật/Tắt Đèn, Quạt, Máy bơm, Điều hòa",
                        "Không có quyền thêm thành viên hoặc gửi link mời",
                        "Bị chặn Mở Cửa chính (D1) & Còi báo động (D8)",
                    ]
                    if target_tier == 2
                    else [
                        "Chỉ bật/tắt đèn & quạt cơ bản",
                        "Không có phần gửi link mời cấp dưới",
                    ]
                ),
            }
            self.accounts.append(acc)
        else:
            acc.pop("password_plain_hint", None)
            acc["display_name"] = pend["display_name"]
            acc["tier"] = target_tier
            acc["saved_tier"] = target_tier
            acc["role"] = role_str
            acc["role_label"] = role_lbl
            acc["permission_active"] = True
            acc["permission_status"] = "ACTIVE"
            acc["permission_label"] = f"CÓ QUYỀN (Tầng {target_tier})"
            acc["password_hash"] = hash_password(issued_pw)
            acc["google_linked"] = True
            acc["invited_by"] = pend["issuer_name"]
            acc["needs_first_page_voice_enroll"] = True
            acc["reading_prompt"] = reading_prompt

        self._save_accounts()
        del self.pending_invite_registrations[clean_email]

        self._log_event(
            layer="Đăng ký Link Mời Hoàn Tất -> Chờ Thu Âm Trang Đầu",
            action="invite_account_created",
            email=clean_email,
            status="PASS",
            detail=(
                f"Đã xác nhận Gmail OTP & cấp mật khẩu cho {acc['display_name']} (Tầng {target_tier}). "
                f"Chuyển vào Trang Đầu hiển thị câu mẫu để giữ thu âm giọng nói gốc!"
            ),
            source=source,
            extra={"reading_prompt": reading_prompt, "tier": target_tier},
        )

        return {
            "ok": True,
            "account": acc,
            "needs_first_page_voice_enroll": True,
            "reading_prompt": reading_prompt,
            "message": (
                f"🎉 Đăng ký thành công tài khoản {acc['display_name']} (Tầng {target_tier})! "
                f"Khi vào Trang Đầu, hãy NHẤN VÀ GIỮ nút thu âm và đọc dòng chữ mẫu để lưu giọng nói gốc lên Server!"
            ),
        }

    def complete_first_page_voice_enrollment(
        self,
        email: str,
        spoken_text: str = "",
        pcm16k_b64: str = "",
        measured_f0_hz: float | None = None,
        hold_duration_sec: float = 3.2,
        source_device: str = "Trang Đầu Web / App Samsung S9 (Nhấn & Giữ)",
        samples_b64: list[str] | None = None,
        self_check_pcm_b64: str = "",
        self_check_pcm_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Khi người dùng mới vào Trang Đầu, đọc dòng chữ mẫu hiển thị trên màn hình và giữ nút thu âm."""
        acc = self.find_account(email)
        if not acc:
            return {
                "ok": False,
                "status_code": 400,
                "error": f"Không tìm thấy tài khoản '{email}' để lưu mẫu giọng trang đầu!",
            }

        enr_res = self.recognize_or_enroll_voice_from_device(
            mode="enroll",
            pcm16k_b64=pcm16k_b64,
            measured_f0_hz=measured_f0_hz,
            email=acc["email"],
            target_name=acc["display_name"],
            target_tier=acc["tier"],
            password="",
            source_device=source_device,
            samples_b64=samples_b64,
            self_check_pcm_b64=self_check_pcm_b64,
            self_check_pcm_bytes=self_check_pcm_bytes,
        )
        if not enr_res.get("ok"):
            return enr_res
        prev_acc_state = copy.deepcopy(self.accounts)
        acc["needs_first_page_voice_enroll"] = False
        acc["voiceprint"]["reading_prompt_verified"] = True
        acc["voiceprint"]["enrolled_phrase"] = spoken_text.strip() or acc.get("reading_prompt", "")
        acc["voiceprint"]["hold_duration_sec"] = round(float(hold_duration_sec or 3.0), 2)
        if not self._save_accounts():
            self.accounts[:] = prev_acc_state
            err_persist = "Lỗi lưu trữ bền vững đám mây (Durable Store). Đã hoàn tác đăng ký giọng nói!"
            return {
                "ok": False,
                "status": "DURABLE_PERSISTENCE_FAILED",
                "status_code": 503,
                "reason": "DURABLE_PERSISTENCE_FAILED",
                "error": err_persist,
                "message": err_persist,
            }

        self._log_event(
            layer="Trang Đầu (Đọc Câu Mẫu & Giữ Thu Âm)",
            action="first_page_voice_enrolled",
            email=acc["email"],
            status="PASS",
            detail=(
                f"{acc['display_name']} (Tầng {acc['tier']}) đã giữ nút thu âm ({acc['voiceprint']['hold_duration_sec']}s) "
                f"đọc câu mẫu trên Trang Đầu -> Lưu giọng gốc F0={acc['voiceprint']['f0_mean_hz']}Hz lên Server!"
            ),
            source=source_device,
            extra={"f0_hz": acc["voiceprint"]["f0_mean_hz"], "phrase": acc["voiceprint"]["enrolled_phrase"]},
        )

        return {
            "ok": True,
            "account": acc,
            "f0_hz": acc["voiceprint"]["f0_mean_hz"],
            "reading_prompt": acc["reading_prompt"],
            "message": (
                f"✅ Đã đọc câu mẫu & giữ thu âm thành công! Server đã lưu mẫu giọng gốc (F0={acc['voiceprint']['f0_mean_hz']}Hz) "
                f"cho {acc['display_name']} (Tầng {acc['tier']})."
            ),
        }

    def set_account_permission_by_voice_or_admin(
        self,
        target_identifier: str,
        enable_permission: bool,
        actor_tier: int = 1,
        spoken_command: str = "",
        source_device: str = "Giọng nói tại nhà (Chủ nhà Cấp 1)",
    ) -> dict[str, Any]:
        """Xử lý khi Chủ nhà (Cấp 1) ra lệnh bằng giọng nói ở nhà để xóa cấp quyền hoặc bật lại quyền."""
        if int(actor_tier) != 1:
            msg = "🚫 Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền xóa cấp quyền hoặc bật lại quyền bằng giọng nói!"
            self._log_event(
                layer="Quản lý Quyền Bằng Giọng Nói",
                action="voice_permission_denied",
                email=target_identifier,
                status="FAIL",
                detail=msg,
                source=source_device,
            )
            return {
                "ok": False,
                "status_code": 403,
                "rbac_blocked": True,
                "error": msg,
                "exact_spoken_reply": msg,
            }

        acc = self.find_account(target_identifier)
        if not acc:
            msg = f"Không tìm thấy tài khoản '{target_identifier}' trong hệ thống để cập nhật quyền."
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        if acc["account_id"] == OWNER_ID or int(acc.get("saved_tier", acc["tier"])) == 1:
            msg = "Không thể xóa cấp quyền của Chủ nhà Cấp 1 Nguyễn Tuấn Anh!"
            return {"ok": False, "error": msg, "exact_spoken_reply": msg}

        prev_perm_accounts = copy.deepcopy(self.accounts)
        if not enable_permission:
            acc["saved_tier"] = int(acc.get("saved_tier") or acc.get("tier") or 2)
            acc["permission_active"] = False
            acc["permission_status"] = "REVOKED"
            acc["revoked_at"] = time.time()
            acc["revoked_by"] = OWNER_EMAIL
            acc["permission_label"] = "🚫 KHÔNG CÓ QUYỀN (Đã bị Chủ nhà xóa/tạm thu hồi quyền)"
            if not self._save_accounts():
                self.accounts[:] = prev_perm_accounts
                err_persist = "Lỗi lưu trữ bền vững đám mây (Durable Store). Đã hoàn tác thu hồi quyền!"
                return {
                    "ok": False,
                    "status": "DURABLE_PERSISTENCE_FAILED",
                    "status_code": 503,
                    "error": err_persist,
                    "exact_spoken_reply": err_persist,
                }

            spoken = (
                f"Đã xóa cấp quyền của {acc['display_name']}. "
                f"Tài khoản vẫn còn trên hệ thống nhưng hiện ở trạng thái KHÔNG CÓ QUYỀN."
            )
            self._log_event(
                layer="Giọng Nói Chủ Nhà (Thu Hồi Quyền)",
                action="voice_permission_revoked",
                email=acc["email"],
                status="PASS",
                detail=f"Khẩu lệnh '{spoken_command or 'Xóa cấp quyền'}' -> {spoken}",
                source=source_device,
                extra={"permission_status": "REVOKED", "saved_tier": acc["saved_tier"]},
            )
            return {
                "ok": True,
                "action": "REVOKED",
                "account": acc,
                "exact_spoken_reply": spoken,
                "message": f"🚫 {spoken}",
            }
        else:
            restored_tier = int(acc.get("saved_tier") or acc.get("tier") or 2)
            acc["tier"] = restored_tier
            acc["permission_active"] = True
            acc["permission_status"] = "ACTIVE"
            acc.pop("revoked_at", None)
            acc.pop("revoked_by", None)
            acc["permission_label"] = f"CÓ QUYỀN (Tầng {restored_tier})"
            if not self._save_accounts():
                self.accounts[:] = prev_perm_accounts
                err_persist = "Lỗi lưu trữ bền vững đám mây (Durable Store). Đã hoàn tác bật lại quyền!"
                return {
                    "ok": False,
                    "status": "DURABLE_PERSISTENCE_FAILED",
                    "status_code": 503,
                    "error": err_persist,
                    "exact_spoken_reply": err_persist,
                }

            spoken = (
                f"Đã bật lại quyền Tầng {restored_tier} cho {acc['display_name']}. "
                f"Tài khoản đã hoạt động bình thường trở lại như cũ."
            )
            self._log_event(
                layer="Giọng Nói Chủ Nhà (Khôi Phục Quyền)",
                action="voice_permission_restored",
                email=acc["email"],
                status="PASS",
                detail=f"Khẩu lệnh '{spoken_command or 'Bật lại quyền'}' -> {spoken}",
                source=source_device,
                extra={"permission_status": "ACTIVE", "restored_tier": restored_tier},
            )
            return {
                "ok": True,
                "action": "RESTORED",
                "account": acc,
                "exact_spoken_reply": spoken,
                "message": f"✅ {spoken}",
            }

    def parse_and_execute_voice_permission_command(
        self,
        spoken_text: str,
        actor_tier: int = 1,
        source_device: str = "Thiết bị Nhà Thông Minh",
    ) -> dict[str, Any] | None:
        """Nhận diện tự nhiên câu nói xóa quyền / bật lại quyền của Chủ nhà trên thiết bị."""
        t_low = spoken_text.strip().lower()
        if not t_low:
            return None

        revoke_keywords = (
            "xóa quyền",
            "xóa cấp quyền",
            "thu hồi quyền",
            "tắt quyền",
            "khóa quyền",
            "hủy quyền",
            "cắt quyền",
        )
        restore_keywords = (
            "bật lại quyền",
            "cấp lại quyền",
            "mở lại quyền",
            "khôi phục quyền",
            "bật quyền lại",
            "cho phép lại",
        )

        is_revoke = any(k in t_low for k in revoke_keywords)
        is_restore = any(k in t_low for k in restore_keywords)
        if not is_revoke and not is_restore:
            return None

        if int(actor_tier) != 1:
            msg = "🚫 Chỉ Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) mới có quyền xóa cấp quyền hoặc bật lại quyền bằng giọng nói!"
            self._log_event(
                layer="Quản lý Quyền Bằng Giọng Nói",
                action="voice_permission_denied",
                email="unknown",
                status="FAIL",
                detail=msg,
                source=source_device,
            )
            return {
                "ok": False,
                "status_code": 403,
                "rbac_blocked": True,
                "error": msg,
                "exact_spoken_reply": msg,
            }

        matched_acc: dict[str, Any] | None = None
        for acc in self.accounts:
            if acc["account_id"] == OWNER_ID:
                continue
            name_low = acc["display_name"].lower()
            short_name = name_low.split("(")[0].strip()
            if short_name and short_name in t_low:
                matched_acc = acc
                break
            if acc["account_id"].replace("_", " ") in t_low or acc["email"].lower() in t_low:
                matched_acc = acc
                break

        if not matched_acc:
            if "thành viên a" in t_low or "người nhà a" in t_low:
                matched_acc = self.find_account("thanh_vien_a")
            elif "thành viên b" in t_low or "người nhà b" in t_low:
                matched_acc = self.find_account("thanh_vien_b")
            elif "khách c" in t_low or "khách" in t_low:
                matched_acc = self.find_account("khach_c")

        if not matched_acc:
            return {
                "ok": False,
                "error": f"Không nhận diện được tên tài khoản cần {'bật lại quyền' if is_restore else 'xóa quyền'} trong câu: '{spoken_text}'",
                "exact_spoken_reply": "Xin vui lòng nói rõ tên người cần xóa quyền hoặc bật lại quyền.",
            }

        return self.set_account_permission_by_voice_or_admin(
            target_identifier=matched_acc["email"],
            enable_permission=bool(is_restore),
            actor_tier=actor_tier,
            spoken_command=spoken_text,
            source_device=source_device,
        )
