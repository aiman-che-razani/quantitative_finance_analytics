"""A curated research universe, not a point-in-time constituent database."""

from axiom.common.models import UNIVERSE, Instrument

EXTRA = "VTI VOO IVV VT VEA VWO AGG BND LQD HYG TIP SHY BIL IAU SGOL SIVR XLF XLK XLE XLY XLP XLV XLI XLU XLB XLRE XLC VGT VHT VFH VDE VNQ IYR IYT XBI IBB SMH SOXX KRE KBE USMV MTUM QUAL VLUE VIG VYM DVY SCHD RSP SPLV".split()
UNIVERSE_60 = UNIVERSE + [Instrument(symbol=s, exchange="UNVERIFIED") for s in EXTRA]


def benchmark_universe(count: int = 342):
    if not 1 <= count <= 342:
        raise ValueError("benchmark universe must contain 1..342 instruments")
    return [Instrument(symbol=f"SIM{i:04d}", exchange="SIMULATED") for i in range(count)]
