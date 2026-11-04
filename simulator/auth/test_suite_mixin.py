"""Module simulator.auth.test_suite_mixin: Bảng Kiểm thử Tự động Toàn diện 14 Kịch bản (TEST-01 -> TEST-14) và Tổng quan Hệ thống."""

from __future__ import annotations

from typing import Any

from simulator.auth.constants_and_crypto import _now_vn


class AuthTestSuiteMixin:
    """Mixin thực thi 14 kịch bản kiểm thử tự động 3 lớp và tổng hợp trạng thái tài khoản (`get_overview`)."""

    accounts: list[dict[str, Any]]
    invite_links: dict[str, dict[str, Any]]
    pending_otps: dict[str, dict[str, Any]]
    pending_invite_registrations: dict[str, dict[str, Any]]
    sessions: dict[str, dict[str, Any]]
    verification_logs: list[dict[str, Any]]
    latest_test_report: dict[str, Any]

    def run_automated_3layer_test_suite(self, send_real_email_on_test1: bool = False) -> dict[str, Any]:
        """Chạy bảng kiểm thử tự động toàn diện 14 kịch bản (TEST-01 -> TEST-14)."""
        cases: list[dict[str, Any]] = []

        self.set_account_permission_by_voice_or_admin("thanh_vien_a", enable_permission=True, actor_tier=1)

        r1 = self.layer1_login(
            "nep94121@gmail.com",
            "TuanAnh@2026",
            login_method="password",
            source="AutoTest-Suite",
            send_gmail=send_real_email_on_test1,
        )
        otp_t1 = r1.get("otp_code_for_test_table", "")
        msg_id_t1 = r1.get("gmail_delivery", {}).get("gmail_message_id", "")
        cases.append({
            "test_id": "TEST-01",
            "layer": "Lớp 1 (Mật khẩu Chủ nhà Cấp 1)",
            "scenario": "Đăng nhập Chủ nhà (nep94121@gmail.com) với mật khẩu ĐÚNG (TuanAnh@2026) & sinh OTP Gmail",
            "expected": "PASS Lớp 1 & Cấp mã OTP 6 số",
            "actual": f"PASS — OTP: {otp_t1}" + (f" (Gmail MsgID: {msg_id_t1})" if msg_id_t1 else ""),
            "passed": bool(r1.get("ok") and otp_t1),
        })

        if send_real_email_on_test1 and msg_id_t1:
            inbox_read = self.read_latest_otp_from_gmail_inbox(message_id=msg_id_t1)
            read_ok = bool(inbox_read.get("ok") and inbox_read.get("extracted_otp") == otp_t1)
            cases.append({
                "test_id": "TEST-02",
                "layer": "Lớp 2 (Đọc Hộp Thư Gmail Thật)",
                "scenario": "Tự động truy cập hộp thư nep94121@gmail.com đọc bức thư vừa gửi để lấy mã OTP xác nhận",
                "expected": f"Đọc đúng mã OTP {otp_t1} từ trong Gmail",
                "actual": f"Đọc từ Gmail MsgID {msg_id_t1}: OTP={inbox_read.get('extracted_otp')}",
                "passed": read_ok,
            })
        else:
            r2 = self.layer1_login(
                "nep94121@gmail.com",
                "MatKhauSai@999",
                login_method="password",
                source="AutoTest-Suite",
                send_gmail=False,
            )
            cases.append({
                "test_id": "TEST-02",
                "layer": "Lớp 1 (Chống Dò Mật Khẩu)",
                "scenario": "Đăng nhập tài khoản Chủ nhà với mật khẩu SAI (MatKhauSai@999)",
                "expected": "Bị chặn ngay tại Lớp 1",
                "actual": r2.get("error", "Đã chặn"),
                "passed": not r2.get("ok", True),
            })

        r3 = self.layer2_verify_otp("nep94121@gmail.com", "000000", source="AutoTest-Suite")
        cases.append({
            "test_id": "TEST-03",
            "layer": "Lớp 2 (Chống Giả Mạo OTP)",
            "scenario": "Nhập mã OTP sai (000000) khác với mã gửi về Gmail",
            "expected": "Bị chặn tại Lớp 2 (Reject OTP)",
            "actual": r3.get("error", "Đã chặn OTP sai"),
            "passed": not r3.get("ok", True),
        })

        r4 = self.layer2_verify_otp("nep94121@gmail.com", otp_t1, source="AutoTest-Suite")
        cases.append({
            "test_id": "TEST-04",
            "layer": "Lớp 2 (Xác Nhận Gmail OTP)",
            "scenario": f"Nhập đúng mã OTP 6 số ({otp_t1}) nhận từ Gmail",
            "expected": "Xác thực Lớp 2 thành công -> Mở cổng Lớp 3",
            "actual": r4.get("message", "OK"),
            "passed": bool(r4.get("ok")),
        })

        inv_t1 = self.get_invite_links_for_account("nep94121@gmail.com")
        tiers_t1 = inv_t1.get("allowed_target_tiers", [])
        cases.append({
            "test_id": "TEST-05",
            "layer": "Phân Cấp Link Mời (Cấp 1)",
            "scenario": "Kiểm tra đường link mời của Cấp 1 (Nguyễn Tuấn Anh) gửi xuống cấp dưới",
            "expected": "Có 2 đường link mời: Cấp 2 (Người nhà) và Cấp 3 (Khách)",
            "actual": f"Số link: {len(inv_t1.get('links', []))} (Cấp được mời: {tiers_t1})",
            "passed": bool(inv_t1.get("can_invite") and tiers_t1 == [2, 3]),
        })

        inv_t2 = self.get_invite_links_for_account("thanhviena.hust@gmail.com")
        tiers_t2 = inv_t2.get("allowed_target_tiers", [])
        try_t2_to_t2 = self.create_custom_invite_link("thanhviena.hust@gmail.com", target_tier=2, source="AutoTest-Suite")
        cases.append({
            "test_id": "TEST-06",
            "layer": "Phân Cấp Link Mời (Cấp 2)",
            "scenario": "Cấp 2 gửi link xuống cấp dưới (Chỉ được mời Cấp 3, thử tạo link Cấp 2 phải bị chặn)",
            "expected": "Chỉ có 1 link mời Cấp 3 & Chặn tạo link Cấp 2",
            "actual": f"Link Cấp 2 được phép: {tiers_t2} | Thử tạo link Cấp 2 -> {try_t2_to_t2.get('error', '')[:65]}",
            "passed": bool(inv_t2.get("can_invite") and tiers_t2 == [3] and not try_t2_to_t2.get("ok", True)),
        })

        inv_t3 = self.get_invite_links_for_account("khachc.guest@gmail.com")
        try_t3_invite = self.create_custom_invite_link("khachc.guest@gmail.com", target_tier=3, source="AutoTest-Suite")
        cases.append({
            "test_id": "TEST-07",
            "layer": "Phân Cấp Link Mời (Cấp 3)",
            "scenario": "Kiểm tra tài khoản Cấp 3 (Khách C): Không có phần gửi link mời xuống cấp dưới",
            "expected": "0 đường link mời (can_invite=False) & Chặn tạo link",
            "actual": f"can_invite={inv_t3.get('can_invite')}, links={len(inv_t3.get('links', []))} | {inv_t3.get('rule_explanation')}",
            "passed": bool(not inv_t3.get("can_invite") and len(inv_t3.get("links", [])) == 0 and not try_t3_invite.get("ok", True)),
        })

        reg_start = self.start_invite_oauth_registration(
            invite_code="INV-T1-TO-TIER2",
            google_email="emgai.invite@gmail.com",
            display_name="Em Gái (Đăng ký qua Link Cấp 2)",
            custom_password="EmGai@2026",
            send_gmail=send_real_email_on_test1,
            source="AutoTest-Invite-OAuth",
        )
        invite_otp = reg_start.get("otp_code_for_test", "")
        reg_verify = self.verify_invite_otp_and_create_account(
            email="emgai.invite@gmail.com",
            otp_input=invite_otp,
            source="AutoTest-Invite-OAuth",
        )
        cases.append({
            "test_id": "TEST-08",
            "layer": "Link Mời + Google OAuth + Gmail OTP",
            "scenario": "Ấn vào link INV-T1-TO-TIER2 -> Đăng nhập Google OAuth -> Xác nhận OTP Gmail để cấp mật khẩu",
            "expected": "Tạo tài khoản Cấp 2 & Bật cờ hiện dòng chữ mẫu thu âm ở Trang Đầu",
            "actual": f"Đã tạo: {reg_verify.get('account', {}).get('display_name')} (Tầng {reg_verify.get('account', {}).get('tier')}) — Chờ thu âm trang đầu: {reg_verify.get('needs_first_page_voice_enroll')}",
            "passed": bool(reg_verify.get("ok") and reg_verify.get("needs_first_page_voice_enroll") is True),
        })

        prompt_txt = reg_verify.get("reading_prompt", "")
        fp_enroll = self.complete_first_page_voice_enrollment(
            email="emgai.invite@gmail.com",
            spoken_text=prompt_txt,
            measured_f0_hz=206.0,
            hold_duration_sec=3.5,
            source_device="Trang Đầu (Nhấn & Giữ Thu Âm)",
        )
        cases.append({
            "test_id": "TEST-09",
            "layer": "Trang Đầu (Đọc Câu Mẫu & Giữ Thu Âm)",
            "scenario": "Vào Trang Đầu hiển thị câu mẫu -> Người dùng đọc và giữ thu âm (3.5s, F0=206Hz) đẩy lên Server",
            "expected": "Server lưu mẫu giọng gốc (voiceprint.enrolled=True) & tắt nhắc thu âm",
            "actual": fp_enroll.get("message", ""),
            "passed": bool(fp_enroll.get("ok") and fp_enroll.get("account", {}).get("voiceprint", {}).get("enrolled")),
        })

        rec_new = self.recognize_or_enroll_voice_from_device(
            mode="recognize",
            measured_f0_hz=205.5,
            email="emgai.invite@gmail.com",
            source_device="Samsung Galaxy S9 (App Android)",
        )
        cases.append({
            "test_id": "TEST-10",
            "layer": "Lớp 3 (Server Nhận Diện Giọng Mới)",
            "scenario": "Người vừa đăng ký nói vào Điện thoại (F0=205.5Hz) -> Server tự đối chiếu mẫu giọng trang đầu",
            "expected": "Server nhận diện đúng Em Gái (Tầng 2) & Mở khóa 3 Lớp",
            "actual": f"Nhận diện: {rec_new.get('speaker_name')} (Tầng {rec_new.get('tier')}, Cosine={rec_new.get('cosine_score')})",
            "passed": bool(rec_new.get("ok") and rec_new.get("tier") == 2),
        })

        rev_cmd = self.parse_and_execute_voice_permission_command(
            spoken_text="Xóa cấp quyền của Thành viên A ngay lập tức",
            actor_tier=1,
            source_device="Mic Nhà Thông Minh (Chủ nhà Cấp 1)",
        )
        login_after_revoke = self.layer1_login(
            "thanhviena.hust@gmail.com",
            "GiaDinh@123",
            login_method="password",
            source="AutoTest-RevokeCheck",
            send_gmail=False,
        )
        cases.append({
            "test_id": "TEST-11",
            "layer": "Giọng Nói Chủ Nhà (Xóa Cấp Quyền)",
            "scenario": "Chủ nhà nói: 'Xóa cấp quyền của Thành viên A' -> Tài khoản vẫn còn nhưng hiện KHÔNG CÓ QUYỀN",
            "expected": "Tài khoản tồn tại (account_exists=True) nhưng bị chặn (permission_status=REVOKED)",
            "actual": f"{rev_cmd.get('exact_spoken_reply', '') if rev_cmd else ''} | Khi đăng nhập hiện: {login_after_revoke.get('permission_label')}",
            "passed": bool(
                rev_cmd
                and rev_cmd.get("ok")
                and login_after_revoke.get("account_exists") is True
                and login_after_revoke.get("permission_status") == "REVOKED"
            ),
        })

        voice_after_revoke = self.recognize_or_enroll_voice_from_device(
            mode="recognize",
            measured_f0_hz=198.0,
            email="thanhviena.hust@gmail.com",
            source_device="Samsung Galaxy S9 (App Android)",
        )
        cases.append({
            "test_id": "TEST-12",
            "layer": "Chặn Giọng Nói Khi Đã Thu Hồi Quyền",
            "scenario": "Thành viên A (đang bị xóa quyền) nói lệnh điều khiển thiết bị qua Điện thoại",
            "expected": "Server nhận ra giọng nhưng chặn và báo 'TÀI KHOẢN HIỆN KHÔNG CÓ QUYỀN'",
            "actual": voice_after_revoke.get("error", ""),
            "passed": bool(not voice_after_revoke.get("ok", True) and voice_after_revoke.get("permission_status") == "REVOKED"),
        })

        res_cmd = self.parse_and_execute_voice_permission_command(
            spoken_text="Bật lại quyền cho Thành viên A như cũ",
            actor_tier=1,
            source_device="Mic Nhà Thông Minh (Chủ nhà Cấp 1)",
        )
        login_after_restore = self.layer1_login(
            "thanhviena.hust@gmail.com",
            "GiaDinh@123",
            login_method="password",
            source="AutoTest-RestoreCheck",
            send_gmail=False,
        )
        cases.append({
            "test_id": "TEST-13",
            "layer": "Giọng Nói Chủ Nhà (Bật Lại Quyền)",
            "scenario": "Chủ nhà nói: 'Bật lại quyền cho Thành viên A' -> Tài khoản được cấp lại quyền Tầng 2 như cũ",
            "expected": "Khôi phục ACTIVE (Tầng 2) & Đăng nhập hoạt động lại bình thường",
            "actual": f"{res_cmd.get('exact_spoken_reply', '') if res_cmd else ''} | Đăng nhập lại: OK={login_after_restore.get('ok')} (Tầng {login_after_restore.get('account', {}).get('tier')})",
            "passed": bool(
                res_cmd
                and res_cmd.get("ok")
                and login_after_restore.get("ok") is True
                and login_after_restore.get("account", {}).get("tier") == 2
            ),
        })

        r14 = self.recognize_or_enroll_voice_from_device(
            mode="recognize",
            measured_f0_hz=262.0,
            source_device="Samsung Galaxy S9 (App Android)",
        )
        cases.append({
            "test_id": "TEST-14",
            "layer": "Lớp 3 (Chặn Giọng Người Lạ)",
            "scenario": "Gửi mẫu thu âm Giọng lạ chưa đăng ký (F0=262.0Hz) từ Điện thoại lên Server",
            "expected": "Server từ chối & cảnh báo Người lạ (BLOCKED)",
            "actual": r14.get("error", "Đã chặn người lạ"),
            "passed": not r14.get("ok", True),
        })

        passed_count = sum(1 for c in cases if c["passed"])
        self.latest_test_report = {
            "ok": passed_count == len(cases),
            "executed_at": _now_vn(),
            "total_cases": len(cases),
            "passed_cases": passed_count,
            "summary": f"Đạt {passed_count}/{len(cases)} kịch bản kiểm thử toàn diện (3 Lớp + Phân cấp Link Mời + OAuth Gmail OTP + Thu âm Trang Đầu + Giọng nói Xóa/Bật Quyền)",
            "cases": cases,
        }
        return self.latest_test_report

    def get_overview(self, active_email: str = "nep94121@gmail.com") -> dict[str, Any]:
        if not self.latest_test_report:
            self.run_automated_3layer_test_suite(send_real_email_on_test1=False)
        safe_accounts = []
        for acc in self.accounts:
            self._normalize_account_fields(acc)
            email_key = acc["email"].lower()
            pend = self.pending_otps.get(email_key)
            sess = self.sessions.get(email_key)
            inv_bundle = self.get_invite_links_for_account(acc["email"])
            safe_accounts.append({
                "account_id": acc["account_id"],
                "email": acc["email"],
                "display_name": acc["display_name"],
                "name": acc["display_name"],
                "tier": acc["tier"],
                "saved_tier": acc.get("saved_tier", acc["tier"]),
                "role": acc["role"],
                "role_label": acc["role_label"],
                "permission_active": acc.get("permission_active", True),
                "active": acc.get("permission_active", True),
                "permission_status": acc.get("permission_status", "ACTIVE"),
                "permission_label": acc.get("permission_label", f"CÓ QUYỀN (Tầng {acc['tier']})"),
                "password_hint": acc.get("password_plain_hint", "***"),
                "google_linked": acc.get("google_linked", False),
                "invited_by": acc.get("invited_by", "SYSTEM_ROOT"),
                "needs_first_page_voice_enroll": acc.get("needs_first_page_voice_enroll", False),
                "voice_verified": acc.get("voice_verified", not acc.get("needs_first_page_voice_enroll", False)),
                "voice_enrolled": bool(acc.get("voiceprint", {}).get("enrolled", False) or acc.get("voice_verified", False)),
                "reading_prompt": acc.get("reading_prompt", ""),
                "voiceprint": acc.get("voiceprint", {}),
                "permissions": acc.get("permissions", []),
                "invite_links_bundle": inv_bundle,
                "active_otp": pend.get("otp_code") if pend else None,
                "layer2_verified": bool(pend.get("verified_layer2")) if pend else False,
                "layer3_verified": bool(sess.get("all_3_layers_passed")) if sess else False,
                "last_session": sess,
            })
        recent_logs_norm = []
        for lg in self.verification_logs[:40]:
            recent_logs_norm.append({
                **lg,
                "time": lg.get("time_vn", ""),
                "event": lg.get("action") or lg.get("layer") or "Xác thực",
            })
        allowlist_items = self.get_family_email_allowlist()
        return {
            "ok": True,
            "server_time_vn": _now_vn(),
            "accounts": safe_accounts,
            "family_email_allowlist": allowlist_items,
            "family_allowlist": allowlist_items,
            "invite_links": list(self.invite_links.values()),
            "active_invite_bundle": self.get_invite_links_for_account(active_email),
            "pending_otps": list(self.pending_otps.values()),
            "pending_invite_registrations": list(self.pending_invite_registrations.values()),
            "active_sessions": list(self.sessions.values()),
            "verification_logs": recent_logs_norm,
            "recent_logs": recent_logs_norm,
            "test_report": self.latest_test_report,
        }
