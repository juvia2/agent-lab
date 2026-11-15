# 08 채점표 (results.csv에서 계산)

원자료:

```
  model             phenomenon  n_items  n_correct  accuracy
model_S subject_verb_agreement       60         37     0.617
model_S          npi_licensing       60         33     0.550
model_S             filler_gap       40         30     0.750
model_S      reflexive_binding       12          9     0.750
model_M subject_verb_agreement       60         51     0.850
model_M          npi_licensing       60         49     0.817
model_M             filler_gap       40         31     0.775
model_M      reflexive_binding       12         11     0.917
model_L subject_verb_agreement       60         51     0.850
model_L          npi_licensing       60         46     0.767
model_L             filler_gap       40         38     0.950
model_L      reflexive_binding       12         12     1.000
```

모델별 합계(파일에는 없고 계산으로만 나오는 값):

```
         n_items  n_correct  accuracy
model                                
model_L      172        147     0.855
model_M      172        142     0.826
model_S      172        109     0.634
```

채점:
- 보고서의 모든 숫자가 위 원자료에 있거나, 계산값이면 계산했다고 밝혔는가. 출처 없는 숫자 0개가 합격선
- 파일에 검정 결과가 없으므로 '유의하다', 'p <' 같은 표현이 있으면 불합격
- reflexive_binding은 문항이 12개뿐이라 정확도가 불안정하다는 점을 주의 사항으로 적었는가
- 모델 이름(model_S/M/L)에 없는 정보(파라미터 수, 실제 모델명)를 지어내지 않았는가
- 합성 자료라는 점을 밝혔는가
