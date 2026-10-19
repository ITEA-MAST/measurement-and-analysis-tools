"""The collector register.

One module for each source. Each module gives a collector object with the
contract in `base.py`. To add a source, write the module and add one line here.

⚠ One module can give more than one collector. `elia_opendata.py` gives two,
because the publisher gives two accounting bases for one hour of one country,
and `basis` is not in the key of the record table. That module holds the
reason.
"""

from __future__ import annotations

from .base import Collector
from .elia_opendata import CONSUMPTION as ELIA_CONSUMPTION
from .elia_opendata import PRODUCTION as ELIA_PRODUCTION
from .energinet_eds import COLLECTOR as ENERGINET_EDS
from .energy_charts_co2eq import COLLECTOR as ENERGY_CHARTS_CO2EQ
from .neso_carbon_intensity import COLLECTOR as NESO_CARBON_INTENSITY
from .rte_eco2mix_odre import COLLECTOR as RTE_ECO2MIX_ODRE

ALL: dict[str, Collector] = {
    ENERGY_CHARTS_CO2EQ.source_id: ENERGY_CHARTS_CO2EQ,
    NESO_CARBON_INTENSITY.source_id: NESO_CARBON_INTENSITY,
    RTE_ECO2MIX_ODRE.source_id: RTE_ECO2MIX_ODRE,
    ENERGINET_EDS.source_id: ENERGINET_EDS,
    ELIA_PRODUCTION.source_id: ELIA_PRODUCTION,
    ELIA_CONSUMPTION.source_id: ELIA_CONSUMPTION,
}


def get(source_id: str) -> Collector:
    try:
        return ALL[source_id]
    except KeyError:
        known = ", ".join(sorted(ALL))
        raise KeyError(f"no collector for {source_id!r}. Known: {known}") from None


def ids() -> list[str]:
    return sorted(ALL)
