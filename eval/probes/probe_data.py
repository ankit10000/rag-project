"""All scorer probes: the 72 Phase D probe ids (some corrected) plus the Phase E2 additions."""
from eval.probes.probes_e2 import E2_PROBES
from eval.probes.probes_phase_d import PHASE_D_PROBES

PROBES = PHASE_D_PROBES + E2_PROBES
