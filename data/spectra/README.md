# 실측 스펙트럼 곡선

여기에 파일이 있으면 파라메트릭 근사 대신 **무조건 이쪽이 쓰인다.**

## 왜 중요한가

파라메트릭 근사(`center_nm` + `fwhm_nm`)는 피크 위치는 맞지만 **날개가 틀리다.**
그런데 광학 게이트의 두 핵심 판정 — 여기광 차단(OD)과 채널 간 크로스토크 —
은 전적으로 날개에서 결정된다.

근사 스펙트럼이 하나라도 섞이면 게이트는:

- `evidence: assumed` → `advances: NO` (판정이 제안을 통과시키지 못함)
- 차단 요구를 5 OD → **7 OD**로 상향
- 필터 제거 제안을 `remove`가 아니라 `candidate`로 강등

즉 **실측 곡선을 넣기 전까지는 어떤 광학 구성도 확정되지 않는다.**

## 형식

2열 텍스트/CSV. 구분자는 공백·탭·쉼표 아무거나.

```
# wavelength_nm   value
400               0.0012
401               0.0013
...
```

- 주석: `#` `;` `//` `%` 로 시작하는 줄
- 값이 1.5를 넘으면 **퍼센트로 간주해 100으로 나눈다** (자동 감지)
- 300–1100 nm 격자(1 nm)로 리샘플된다. 범위 밖은 0으로 채움

## 어디서 받나

| 대상 | 출처 |
|---|---|
| 필터·다이크로익 | Semrock/IDEX, Chroma 제품 페이지의 ASCII 다운로드 |
| 형광 염료 | [FPbase](https://www.fpbase.org) — CSV 내보내기 |
| 카메라 QE | 제조사 데이터시트 (그래프만 있으면 디지타이즈) |
| 광원 라인 | Lumencor 데이터시트 |

## 연결하기

```yaml
# data/filters.yaml
"FF01-692/40":
  kind: bandpass
  curve: ff01-692-40.txt        # ← data/spectra/ 기준 상대경로

# data/fluorophores.yaml
ATTO647N:
  curves:
    absorption: atto647n_abs.csv
    emission:   atto647n_em.csv

# data/detectors.yaml
Prime95B:
  qe_curve: prime95b_qe.txt      # 또는 {파장: QE} 인라인 매핑
```

## 파일 이름 규칙

부품번호를 그대로. 소문자, `/`는 `-`로.
`FF01-692/40` → `ff01-692-40.txt`

## 현재 상태

2026-08-10: ATTO 488, ATTO 550(요청받은 "ATTO 555"의 실체 확인 안 됨 — 아래
참고)의 PBS 실측 곡선을 ATTO-TEC/Leica 공식 다운로드에서 확보해 넣음
(`atto488_abs/em.txt`, `atto550_abs/em.txt`). FITC·Acridine Orange는
PhotochemCAD 실측 곡선을 받긴 했지만(`fitc_*.txt`, `acridineorange_*.txt`)
**용매/결합상태가 실사용 조건과 달라 `data/fluorophores.yaml`의 `curves:`에
일부러 연결하지 않았다** — 각 파일 상단 주석과 yaml의 해당 dye note 참고.

나머지 다이(Cy5, Alexa Fluor 647/488/555, ATTO 647N, YOYO-1, SYTO 61,
Dragon Green)는 이번 조사에서 진짜 (파장, 세기) 실측 곡선을 못 구했다 —
FPbase는 자동 fetch 자체가 Cloudflare에 막히고, AAT Bioquest 뷰어는
이메일 요청만 되고, Thermo SpectraViewer는 JS 앱이라 헤드리스 fetch가
타임아웃되고, fluorophores.tugraz.at은 목록 페이지(피크값)는 살아있지만
상세 페이지가 500 에러를 낸다. 브라우저로 직접 받아야 하면 각 dye의
`note:`에 적어둔 URL을 참고. 그 전까지는 파라메트릭 근사로 돌고,
크로스토크/차단 최종 판정은 여전히 confidence low다. 의도된 동작이다.
