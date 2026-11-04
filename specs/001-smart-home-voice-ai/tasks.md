# Dependency-Ordered Tasks (`/speckit.tasks`)

## Phase 1: Foundation & Constitution Lock
- [x] **T001** Khởi tạo `.specify/memory/constitution.md` khóa 6 Điều bất biến của hệ thống Smart Home Voice AI.
- [x] **T002** Tải bộ công cụ chuẩn `github/spec-kit` (9 lệnh `constitution` $\rightarrow$ `converge` + scripts Python) vào `.specify/`.

## Phase 2: Core Slice Stabilization (Zero-Overlap)
- [x] **T003** [Slice A - `simulator/voice_auth.py`] Khử Sub-harmonic Octave Error (`87.4 Hz`), khóa mẫu giả lập Cấp 2/3 chưa thu âm không cho cướp giọng Mic của Chủ nhà Cấp 1, và áp dụng 3 mức câu trả lời chặn Người lạ.
- [x] **T004** [Slice B - `simulator/server.py`] Tách `gemini_receive_loop` tự phục hồi ngầm và thêm cổng `_ensure_current_mic_utterance_verified` kiểm tra 1 lần/câu nói.
- [x] **T005** [Slice D - `simulator/static/app.js` & `index.html`] Đồng bộ phát âm thanh chặn Lần 1 / Lần 2, ngắt âm Lần 3+, và thêm cache-busting `?v=20261103_v3`.

## Phase 3: Automated Convergence Gate (`/speckit.converge`)
- [x] **T006** Xây dựng công cụ kiểm toán tự động `scripts/speckit_converge.py` và Skill điều phối Team `.agents/skills/github-spec-kit/SKILL.md`.
- [x] **T007** [Remediation `CONV-01`] Sửa lỗi `AttributeError: 'list' object has no attribute 'values'` tại `simulator/server.py` (`_apply_voice_tier_and_sync`) và lỗi `ReferenceError: playCtx is not defined` tại `simulator/static/app.js` (`micProcessor.onaudioprocess`).


## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Vi phạm Điều 2 Hiến pháp: Giọng Chủ nhà factor=1.15 bị chặn ({'authorized': True, 'speaker_id': 'user_voice_thanh_vien_a', 'user_id': 'thanh_vien_a', 'role': 'MEMBER', 'speaker_label': 'Giọng Cấp 2 — Thành viên A (Người nhà - Chặn Cửa & Còi)', 'tier': 2, 'f0_hz': 146.8, 'centroid_hz': 818.5, 'formants_hz': [], 'similarity': 0.97, 'stage1_confidence': 0.97, 'stage2_triggered': False, 'stage2_confidence': None, 'filter_stage_used': 'Tầng 1 (Nhanh 26 chiều)', 'denoise_ms': 1.16, 'stage1_ms': 2.23, 'stage2_ms': 0.0, 'diarization_ms': 3.72, 'total_ms': 7.69, 'noise_removed_db': 15.1, 'fan_noise_detected': False, 'multi_speaker_detected': False, 'speaker_count': 1, 'priority_reason': 'Chỉ có 1 người nói.', 'strike_count': 0, 'should_reply': True, 'silent_ignore': False, 'rejection_speech': ''})

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Vi phạm Điều 2 Hiến pháp: Giọng Chủ nhà factor=1.15 bị chặn ({'authorized': True, 'speaker_id': 'user_voice_thanh_vien_a', 'user_id': 'thanh_vien_a', 'role': 'MEMBER', 'speaker_label': 'Giọng Cấp 2 — Thành viên A (Người nhà - Chặn Cửa & Còi)', 'tier': 2, 'f0_hz': 146.8, 'centroid_hz': 818.5, 'formants_hz': [], 'similarity': 0.97, 'stage1_confidence': 0.97, 'stage2_triggered': False, 'stage2_confidence': None, 'filter_stage_used': 'Tầng 1 (Nhanh 26 chiều)', 'denoise_ms': 1.18, 'stage1_ms': 3.75, 'stage2_ms': 0.0, 'diarization_ms': 3.2, 'total_ms': 8.61, 'noise_removed_db': 15.1, 'fan_noise_detected': False, 'multi_speaker_detected': False, 'speaker_count': 1, 'priority_reason': 'Chỉ có 1 người nói.', 'strike_count': 0, 'should_reply': True, 'silent_ignore': False, 'rejection_speech': ''})

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Vi phạm Điều 2 Hiến pháp: Giọng Chủ nhà factor=1.15 bị chặn ({'authorized': True, 'speaker_id': 'user_voice_thanh_vien_a', 'user_id': 'thanh_vien_a', 'role': 'MEMBER', 'speaker_label': 'Giọng Cấp 2 — Thành viên A (Người nhà - Chặn Cửa & Còi)', 'tier': 2, 'f0_hz': 146.8, 'centroid_hz': 818.5, 'formants_hz': [], 'similarity': 0.97, 'stage1_confidence': 0.97, 'stage2_triggered': False, 'stage2_confidence': None, 'filter_stage_used': 'Tầng 1 (Nhanh 26 chiều)', 'denoise_ms': 1.2, 'stage1_ms': 2.09, 'stage2_ms': 0.0, 'diarization_ms': 3.17, 'total_ms': 6.87, 'noise_removed_db': 15.1, 'fan_noise_detected': False, 'multi_speaker_detected': False, 'speaker_count': 1, 'priority_reason': 'Chỉ có 1 người nói.', 'strike_count': 0, 'should_reply': True, 'silent_ignore': False, 'rejection_speech': ''})

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Vi phạm Điều 2 Hiến pháp: Giọng Chủ nhà factor=1.15 bị chặn ({'authorized': True, 'speaker_id': 'user_voice_thanh_vien_a', 'user_id': 'thanh_vien_a', 'role': 'MEMBER', 'speaker_label': 'Giọng Cấp 2 — Thành viên A (Người nhà - Chặn Cửa & Còi)', 'tier': 2, 'f0_hz': 146.8, 'centroid_hz': 818.5, 'formants_hz': [], 'similarity': 0.97, 'stage1_confidence': 0.97, 'stage2_triggered': False, 'stage2_confidence': None, 'filter_stage_used': 'Tầng 1 (Nhanh 26 chiều)', 'denoise_ms': 1.22, 'stage1_ms': 2.41, 'stage2_ms': 0.0, 'diarization_ms': 3.33, 'total_ms': 7.47, 'noise_removed_db': 15.1, 'fan_noise_detected': False, 'multi_speaker_detected': False, 'speaker_count': 1, 'priority_reason': 'Chỉ có 1 người nói.', 'strike_count': 0, 'should_reply': True, 'silent_ignore': False, 'rejection_speech': ''})

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-07** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/devops: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-08** Không kết nối được Live Server tại http://127.0.0.1:8088/api/voice_auth/profiles: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-09** Không kết nối được Live Server tại http://127.0.0.1:8088/api/auth3/overview: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-10** Không kết nối được Live Server tại http://127.0.0.1:8088/api/server_logs_and_db: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-11** Lỗi kiểm thử WebSocket /ws trực tiếp: [WinError 1225] The remote computer refused the network connection

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Vi phạm Điều 2 Hiến pháp: Giọng Chủ nhà factor=1.15 bị chặn ({'authorized': True, 'speaker_id': 'user_voice_thanh_vien_a', 'user_id': 'thanh_vien_a', 'role': 'MEMBER', 'speaker_label': 'Giọng Cấp 2 — Thành viên A (Người nhà - Chặn Cửa & Còi)', 'tier': 2, 'f0_hz': 146.8, 'centroid_hz': 818.5, 'formants_hz': [], 'similarity': 0.97, 'stage1_confidence': 0.97, 'stage2_triggered': False, 'stage2_confidence': None, 'filter_stage_used': 'Tầng 1 (Nhanh 26 chiều)', 'denoise_ms': 1.77, 'stage1_ms': 2.56, 'stage2_ms': 0.0, 'diarization_ms': 5.04, 'total_ms': 9.93, 'noise_removed_db': 15.1, 'fan_noise_detected': False, 'multi_speaker_detected': False, 'speaker_count': 1, 'priority_reason': 'Chỉ có 1 người nói.', 'strike_count': 0, 'should_reply': True, 'silent_ignore': False, 'rejection_speech': ''})

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Vi phạm Điều 2 Hiến pháp: Giọng Chủ nhà factor=1.15 bị chặn ({'authorized': True, 'speaker_id': 'user_voice_thanh_vien_a', 'user_id': 'thanh_vien_a', 'role': 'MEMBER', 'speaker_label': 'Giọng Cấp 2 — Thành viên A (Người nhà - Chặn Cửa & Còi)', 'tier': 2, 'f0_hz': 146.8, 'centroid_hz': 818.5, 'formants_hz': [], 'similarity': 0.97, 'stage1_confidence': 0.97, 'stage2_triggered': False, 'stage2_confidence': None, 'filter_stage_used': 'Tầng 1 (Nhanh 26 chiều)', 'denoise_ms': 2.04, 'stage1_ms': 1.64, 'stage2_ms': 0.0, 'diarization_ms': 4.25, 'total_ms': 8.66, 'noise_removed_db': 15.1, 'fan_noise_detected': False, 'multi_speaker_detected': False, 'speaker_count': 1, 'priority_reason': 'Chỉ có 1 người nói.', 'strike_count': 0, 'should_reply': True, 'silent_ignore': False, 'rejection_speech': ''})

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Vi phạm Điều 2 Hiến pháp: Giọng Chủ nhà factor=1.15 bị chặn ({'authorized': True, 'speaker_id': 'user_voice_thanh_vien_a', 'user_id': 'thanh_vien_a', 'role': 'MEMBER', 'speaker_label': 'Giọng Cấp 2 — Thành viên A (Đã thu âm giọng thật)', 'tier': 2, 'f0_hz': 146.8, 'centroid_hz': 818.5, 'formants_hz': [], 'similarity': 0.97, 'stage1_confidence': 0.97, 'stage2_triggered': False, 'stage2_confidence': None, 'filter_stage_used': 'Tầng 1 (Nhanh 26 chiều)', 'denoise_ms': 1.16, 'stage1_ms': 1.56, 'stage2_ms': 0.0, 'diarization_ms': 3.16, 'total_ms': 11.85, 'noise_removed_db': 15.1, 'fan_noise_detected': False, 'multi_speaker_detected': False, 'speaker_count': 1, 'priority_reason': 'Chỉ có 1 người nói.', 'strike_count': 0, 'should_reply': True, 'silent_ignore': False, 'rejection_speech': ''})

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Vi phạm Điều 2 Hiến pháp: Giọng Chủ nhà factor=1.28 bị chặn ({'authorized': True, 'speaker_id': 'user_voice_family_a', 'user_id': 'family_a', 'role': 'MEMBER', 'speaker_label': 'Giọng Cấp 2 — Thành viên A (Đã thu âm giọng thật)', 'tier': 2, 'f0_hz': 138.6, 'centroid_hz': 752.0, 'formants_hz': [], 'similarity': 0.97, 'stage1_confidence': 0.97, 'stage2_triggered': False, 'stage2_confidence': None, 'filter_stage_used': 'Tầng 1 (Nhanh 26 chiều)', 'denoise_ms': 1.25, 'stage1_ms': 1.74, 'stage2_ms': 0.0, 'diarization_ms': 4.74, 'total_ms': 14.97, 'noise_removed_db': 15.9, 'fan_noise_detected': False, 'multi_speaker_detected': False, 'speaker_count': 1, 'priority_reason': 'Chỉ có 1 người nói.', 'strike_count': 0, 'should_reply': True, 'silent_ignore': False, 'rejection_speech': ''})

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-07** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/devops: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-08** Không kết nối được Live Server tại http://127.0.0.1:8088/api/voice_auth/profiles: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-09** Không kết nối được Live Server tại http://127.0.0.1:8088/api/auth3/overview: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-10** Không kết nối được Live Server tại http://127.0.0.1:8088/api/server_logs_and_db: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-11** Lỗi kiểm thử WebSocket /ws trực tiếp: [WinError 1225] The remote computer refused the network connection

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-07** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/devops: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-08** Không kết nối được Live Server tại http://127.0.0.1:8088/api/voice_auth/profiles: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-09** Không kết nối được Live Server tại http://127.0.0.1:8088/api/auth3/overview: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-10** Không kết nối được Live Server tại http://127.0.0.1:8088/api/server_logs_and_db: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-11** Lỗi kiểm thử WebSocket /ws trực tiếp: [WinError 1225] The remote computer refused the network connection

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-07** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/devops: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-08** Không kết nối được Live Server tại http://127.0.0.1:8088/api/voice_auth/profiles: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-09** Không kết nối được Live Server tại http://127.0.0.1:8088/api/auth3/overview: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-10** Không kết nối được Live Server tại http://127.0.0.1:8088/api/server_logs_and_db: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-11** Lỗi kiểm thử WebSocket /ws trực tiếp: [WinError 1225] The remote computer refused the network connection

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-07** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/devops: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-08** Không kết nối được Live Server tại http://127.0.0.1:8088/api/voice_auth/profiles: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-09** Không kết nối được Live Server tại http://127.0.0.1:8088/api/auth3/overview: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-10** Không kết nối được Live Server tại http://127.0.0.1:8088/api/server_logs_and_db: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-11** Lỗi kiểm thử WebSocket /ws trực tiếp: [WinError 1225] The remote computer refused the network connection

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-07** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/devops: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-08** Không kết nối được Live Server tại http://127.0.0.1:8088/api/voice_auth/profiles: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-09** Không kết nối được Live Server tại http://127.0.0.1:8088/api/auth3/overview: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-10** Không kết nối được Live Server tại http://127.0.0.1:8088/api/server_logs_and_db: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-11** Lỗi kiểm thử WebSocket /ws trực tiếp: [WinError 1225] The remote computer refused the network connection

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-07** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/devops: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-08** Không kết nối được Live Server tại http://127.0.0.1:8088/api/voice_auth/profiles: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-09** Không kết nối được Live Server tại http://127.0.0.1:8088/api/auth3/overview: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-10** Không kết nối được Live Server tại http://127.0.0.1:8088/api/server_logs_and_db: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-11** Lỗi kiểm thử WebSocket /ws trực tiếp: [WinError 1225] The remote computer refused the network connection

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-07** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/devops: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-08** Không kết nối được Live Server tại http://127.0.0.1:8088/api/voice_auth/profiles: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-09** Không kết nối được Live Server tại http://127.0.0.1:8088/api/auth3/overview: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-10** Không kết nối được Live Server tại http://127.0.0.1:8088/api/server_logs_and_db: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-11** Lỗi kiểm thử WebSocket /ws trực tiếp: [WinError 1225] The remote computer refused the network connection

## Phase Convergence: Remediation Tasks
- [ ] **CONV-01** Không kết nối được Live Server tại http://127.0.0.1:8088/: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-02** Không kết nối được Live Server tại http://127.0.0.1:8088/auth: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-03** Không kết nối được Live Server tại http://127.0.0.1:8088/wokwi: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-04** Không kết nối được Live Server tại http://127.0.0.1:8088/logs: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-05** Không kết nối được Live Server tại http://127.0.0.1:8088/archify: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-06** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/erd: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-07** Không kết nối được Live Server tại http://127.0.0.1:8088/archify/devops: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-08** Không kết nối được Live Server tại http://127.0.0.1:8088/api/voice_auth/profiles: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-09** Không kết nối được Live Server tại http://127.0.0.1:8088/api/auth3/overview: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-10** Không kết nối được Live Server tại http://127.0.0.1:8088/api/server_logs_and_db: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
- [ ] **CONV-11** Lỗi kiểm thử WebSocket /ws trực tiếp: [WinError 1225] The remote computer refused the network connection
