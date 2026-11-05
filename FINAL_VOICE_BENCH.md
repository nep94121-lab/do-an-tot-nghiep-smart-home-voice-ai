# FINAL VOICE BENCH v2 - clean data, leave-one-out (LENOVO CPU i5-13420H) - 2026-11-06 00:25

Owner units (distinct, md5-deduped, VAD 16 kHz mono): test_audio__cac_cau_lenh_cua_sep__cau_1_xin_chao_chu_nha_cap1.wav 2.6s, test_audio__cac_cau_lenh_cua_sep__cau_2_mo_cua_chinh.wav 0.9s, test_audio__cac_cau_lenh_cua_sep__cau_3_dong_cua_chinh.wav 0.7s, test_audio__cac_cau_lenh_cua_sep__cau_4_bat_den_phong_khach.wav 0.7s, test_audio__cac_cau_lenh_cua_sep__cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav 1.6s, test_audio__cac_cau_lenh_cua_sep__cau_6_tat_het_den.wav 0.7s, test_audio__giong_chu_nha_cap1_tuan_anh.wav#0 4.1s, test_audio__giong_chu_nha_cap1_tuan_anh.wav#1 4.1s, test_audio__lich_su_thu_am__giong_cap1_20261104_110554.wav 1.7s
Excluded/dropped: test_audio__bat_den_phong_khach.wav (excluded); test_audio__bat_quat_va_dieu_hoa.wav (excluded); test_audio__cac_cau_lenh_cua_sep__cau_7_dong_het_cua.wav (excluded); test_audio__day_lenh_di_ngu.wav (excluded); test_audio__giong_1_chu_nha_mo_cua.wav (excluded); test_audio__giong_1_kem_tieng_on_quat.wav (excluded); test_audio__hai_nguoi_cung_noi_cap1_va_nguoi_la.wav (excluded); test_audio__hen_gio_5s_tat_den.wav (excluded); test_audio__kich_hoat_di_ngu.wav (excluded); test_audio__lich_su_thu_am__giong_cap1_20261104_110757.wav (dup); test_audio__lich_su_thu_am__giong_cap1_20261104_110844.wav (dup); test_audio__lich_su_thu_am__giong_cap1_20261104_110930.wav (dup); test_audio__lich_su_thu_am__giong_cap1_20261104_111054.wav (dup); test_audio__lich_su_thu_am__giong_cap1_20261104_111206.wav (dup); test_audio__luat_1_chieu_cua_dieu_hoa.wav (excluded); test_audio__mo_cua_chinh.wav (dup); test_audio__reset_he_thong.wav (excluded); test_audio__tat_quat.wav (excluded); voices__level1_commands__cau_1_xin_chao_chu_nha_cap1.wav (dup); voices__level1_commands__cau_2_mo_cua_chinh.wav (dup); voices__level1_commands__cau_3_dong_cua_chinh.wav (dup); voices__level1_commands__cau_4_bat_den_phong_khach.wav (dup); voices__level1_commands__cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav (dup); voices__level1_commands__cau_6_tat_het_den.wav (dup); voices__level1_commands__cau_7_dong_het_cua.wav (dup); voices__level1_owner.wav (dup); datnwt__cau_1_xin_chao_chu_nha_cap1.wav (dup); datnwt__cau_2_mo_cua_chinh.wav (dup); datnwt__cau_3_dong_cua_chinh.wav (dup); datnwt__cau_4_bat_den_phong_khach.wav (dup); datnwt__cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav (dup); datnwt__cau_6_tat_het_den.wav (dup); datnwt__cau_7_dong_het_cua.wav (dup); datnwt__level1_owner.wav (dup); datnwt__level2_bat_den_phong_khach.wav (dup); datnwt__level2_family.wav (dup); datnwt__level2_mo_cua_chinh.wav (dup); datnwt__level2_tat_quat.wav (dup); datnwt__level3_bat_den_phong_khach.wav (dup); datnwt__level3_guest.wav (dup); datnwt__level3_mo_cua_chinh.wav (dup); datnwt__level3_tat_quat.wav (dup)
Protocol: for each owner unit, enroll on K other owner units (clean), test that unit clean + noise SNR20/10, gain -12/+6 dB, opus 24k, phone 8 kHz. Impostors (141): VIVOS 65 speakers x2 + family/generated level-2/3, scored against every fold enrollment.
Genuine trials per config: 63; impostor trials: 1269. NOTE: only 9 distinct owner units exist, so FRR resolution is coarse.

## Accuracy

| Model | Enroll | EER (thr) | FRR@FAR1% (thr) | FRR@FAR0.1% (thr) | EER clean | FRR@FAR1% strangers / family |
|---|---|---|---|---|---|---|
| WeSpeaker ResNet34 ONNX | max of 5 | 1.9% (0.394) | 6.3% (0.473) | 12.7% (0.499) | 0.0% | 6.3% / 0.0% |
| WeSpeaker ResNet34 ONNX | mean of 5 | 3.2% (0.369) | 4.8% (0.435) | 15.9% (0.497) | 0.0% | 4.8% / 0.0% |
| WeSpeaker ResNet34 ONNX | max of 3 | 3.5% (0.365) | 7.9% (0.430) | 22.2% (0.499) | 0.5% | 14.3% / 1.6% |
| WeSpeaker ResNet34 ONNX | mean of 3 | 3.2% (0.360) | 6.3% (0.423) | 15.9% (0.494) | 0.0% | 7.9% / 3.2% |
| CAM++ ONNX | max of 5 | 4.7% (0.515) | 17.5% (0.584) | 27.0% (0.606) | 0.4% | 17.5% / 3.2% |
| CAM++ ONNX | mean of 5 | 3.2% (0.469) | 14.3% (0.549) | 28.6% (0.598) | 0.2% | 14.3% / 1.6% |
| CAM++ ONNX | max of 3 | 6.4% (0.458) | 38.1% (0.572) | 42.9% (0.606) | 8.6% | 39.7% / 6.3% |
| CAM++ ONNX | mean of 3 | 4.8% (0.443) | 15.9% (0.545) | 38.1% (0.609) | 0.4% | 15.9% / 3.2% |

## Speed (4 s probe, ms median / p95; process HIGH priority; CPU load at end 58%, top: System 0%,  0%, Registry 0%, cmd.exe 0%, svchost.exe 0%, cmd.exe 0%)

| Model | size MB | 1 thr full | 1 thr model-only | 2 thr full | 2 thr model-only | 4 thr full | 4 thr model-only |
|---|---|---|---|---|---|---|---|
| WeSpeaker ResNet34 ONNX | 25.3 | 181 / 206 | 282 / 317 | 116 / 126 | 150 / 163 | 91 / 98 | 113 / 131 |
| CAM++ ONNX | 27.9 | 69 / 83 | 103 / 131 | 53 / 64 | 62 / 76 | 50 / 55 | 53 / 57 |

full = VAD + fbank + ONNX + cosine on cau_1 (2.6 s speech after VAD); model-only = ONNX on precomputed fbank of a 4 s probe (longer input, hence slower than "full"). Per-process CPU% in the header was not captured correctly (psutil sampling); total load 58%.

## Mean owner score by condition (max of 5)

| Model | clean | gain+6 | gain-12 | noise10 | noise20 | opus | phone8k |
|---|---|---|---|---|---|---|---|
| WeSpeaker ResNet34 ONNX | 0.678 | 0.671 | 0.678 | 0.528 | 0.610 | 0.635 | 0.549 |
| CAM++ ONNX | 0.728 | 0.729 | 0.728 | 0.597 | 0.692 | 0.668 | 0.621 |

## Owner unit clean scores (leave-one-out, max of 5)

| unit | WeSpeaker ResNet34 ONNX | CAM++ ONNX |
|---|---|---|
| test_audio__cac_cau_lenh_cua_sep__cau_1_xin_chao_chu_nha_cap1.wav | 0.605 | 0.634 |
| test_audio__cac_cau_lenh_cua_sep__cau_2_mo_cua_chinh.wav | 0.715 | 0.724 |
| test_audio__cac_cau_lenh_cua_sep__cau_3_dong_cua_chinh.wav | 0.584 | 0.640 |
| test_audio__cac_cau_lenh_cua_sep__cau_4_bat_den_phong_khach.wav | 0.655 | 0.729 |
| test_audio__cac_cau_lenh_cua_sep__cau_5_bat_quat_tran_va_dieu_hoa_phong_ngu.wav | 0.791 | 0.750 |
| test_audio__cac_cau_lenh_cua_sep__cau_6_tat_het_den.wav | 0.574 | 0.705 |
| test_audio__giong_chu_nha_cap1_tuan_anh.wav#0 | 0.920 | 0.936 |
| test_audio__giong_chu_nha_cap1_tuan_anh.wav#1 | 0.707 | 0.829 |
| test_audio__lich_su_thu_am__giong_cap1_20261104_110554.wav | 0.554 | 0.602 |
