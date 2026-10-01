from datetime import date

import pytest

from bcb_pipeline.config import SerieConfig
from bcb_pipeline.quality import CheckResult, QualityCheckError, exigir_aprovacao

SERIE = SerieConfig(11, "Selic", "diaria", "% a.d.", date(2000, 1, 1))


def test_all_checks_ok_passes() -> None:
    exigir_aprovacao(SERIE, [CheckResult("datas_futuras", 0), CheckResult("valores_nulos", 0)])


def test_any_violation_fails_with_details() -> None:
    resultados = [
        CheckResult("datas_futuras", 0),
        CheckResult("fora_da_faixa", 2, [(date(2024, 1, 2), 99)]),
    ]

    with pytest.raises(QualityCheckError, match=r"série 11 .*fora_da_faixa: 2") as exc:
        exigir_aprovacao(SERIE, resultados)
    assert "datas_futuras" not in str(exc.value)
