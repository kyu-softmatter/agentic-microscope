"""Ray-optics (geometric optics approximation) trap-force model.

Ported from ``D:\\codes\\Geometric_optics_approximation\\GOA_ab.m`` --
Ashkin's closed-form ray-optics model for a single-beam gradient trap acting
on a homogeneous dielectric sphere (Ashkin, Biophys. J. 61:569-582, 1992).

Two discrepancies were found in GOA_ab.m while porting and are NOT
reproduced here:

* ``Qg``'s denominator in GOA_ab.m line 65 is ``1 + R^2 + 2R*sin(2*a_ref)``.
  Ashkin's gradient-efficiency formula uses ``cos(2*a_ref)`` -- at normal
  incidence (a_ref=0) the correct denominator reduces to ``(1+R)^2``, while
  the sin form collapses to 1 regardless of R, which is not physical. This
  module uses cos.
* GOA_ab.m computes the beam waist as ``w0 = lambda0/(NA*pi)`` (line 69).
  Some derivations add an extra medium-index factor,
  ``w0 = lambda0/(NA*n_medium*pi)``, but that is dimensionally inconsistent:
  NA := n*sin(theta_max) already carries the medium index, so it cancels
  against the in-medium wavelength and no free ``n`` should remain. This
  module uses the ``n``-free form.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

C_LIGHT = 299_792_458.0  # m/s


@dataclass(frozen=True)
class Bead:
    """A homogeneous dielectric sphere."""

    radius_m: float
    n: float  # refractive index, e.g. 1.45 for silica at 1064 nm


@dataclass(frozen=True)
class Medium:
    """The immersion medium the bead sits in."""

    n: float = 1.33  # water at 1064 nm
    #: dynamic viscosity, Pa*s. None until supplied -- see
    #: trapping.dynamics.water_viscosity_pa_s() for water; a different
    #: medium (an ATPS phase, a density-matched buffer) needs its own
    #: measured or literature value. Only trapping.checks.check_sampling
    #: (corner frequency / G14) needs this; trap_force does not.
    viscosity_pa_s: float | None = None


@dataclass(frozen=True)
class ObjectiveBeam:
    """The focusing objective and the Gaussian beam it produces."""

    na: float
    wavelength_m: float = 1064e-9

    def theta_max(self, medium: Medium) -> float:
        """Half-angle of the focusing cone (center-focus-edge ray)."""
        sin_theta = self.na / medium.n
        if not 0 < sin_theta <= 1:
            raise ValueError(
                f"NA={self.na} is not achievable in a medium of n={medium.n} "
                f"(NA/n = {sin_theta} must be in (0, 1])"
            )
        return np.arcsin(sin_theta)

    def beam_waist_m(self) -> float:
        """Diffraction-limited waist w0 = lambda0 / (pi * NA).

        NA = n*sin(theta_max) already carries the medium index, so it cancels
        against the in-medium wavelength lambda0/n in the paraxial Gaussian
        relation w0 = (lambda0/n) / (pi * theta_max) -- no explicit n term.
        """
        return self.wavelength_m / (self.na * np.pi)


def ray_optics_regime(bead: Bead, beam: ObjectiveBeam, medium: Medium) -> tuple[str, float]:
    """Classify whether ray optics is a valid approximation for this bead.

    Uses the Mie size parameter x = 2*pi*radius/lambda_medium -- the
    standard dimensionless parameter scattering theory classifies regimes
    by (Bohren & Huffman; van de Hulst, "Light Scattering by Small
    Particles"): x << 1 is the Rayleigh (dipole) regime, x >> 1 is the
    geometric/ray-optics regime, and the region around x ~ 1 is neither --
    full Lorenz-Mie theory (GLMT) is required there, and a ray-optics number
    would be fiction, not a rough-but-useful approximation. This module
    gates on the commonly used rule-of-thumb cutoffs x < 0.3 (Rayleigh) and
    x > 10 (geometric optics); everything in between is "intermediate".

    This is exactly the regime Ashkin's foundational ray-optics paper (and
    every script in the GOA MATLAB folder) operates in: a 2.5 um silica bead
    at 1064 nm in water has x = 2*pi*2.5/(1.064/1.33) = 19.6, solidly in
    "ray_optics".

    Returns (regime, size_parameter_x) where regime is one of
    "ray_optics", "intermediate", "rayleigh".
    """
    lambda_medium = beam.wavelength_m / medium.n
    x = 2 * np.pi * bead.radius_m / lambda_medium
    if x > 10.0:
        return "ray_optics", x
    if x < 0.3:
        return "rayleigh", x
    return "intermediate", x


def _gauss_legendre_grid(lo: float, hi: float, n: int) -> tuple[np.ndarray, np.ndarray]:
    x, w = np.polynomial.legendre.leggauss(n)
    nodes = 0.5 * (hi - lo) * x + 0.5 * (hi + lo)
    weights = 0.5 * (hi - lo) * w
    return nodes, weights


def trap_force(
    power_w: float,
    displacement_m: float,
    bead: Bead,
    medium: Medium,
    beam: ObjectiveBeam,
    *,
    n_points: int = 96,
) -> tuple[float, float]:
    """Radial and axial trap force in newtons, ray-optics model.

    ``power_w`` is the power actually incident on this bead -- already
    divided across simultaneous traps if the beam is split (see
    ``trapping.laser.power_per_trap``). ``displacement_m`` is the bead
    center's lateral (radial) offset from the beam focus; the model assumes
    zero axial offset (bead center in the focal plane).

    Returns ``(f_radial_n, f_axial_n)`` in newtons, following the raw sign
    convention of the MATLAB source (Fy, Fz before its cosmetic
    ``plot(...,-FFy,...)`` negation for display). A stable trap has
    f_radial opposing the sign of ``displacement_m``.

    Integrates Ashkin's closed-form Qs/Qg over the objective's angular
    aperture (polar angle ``a``, azimuth ``b``) with fixed-order
    Gauss-Legendre quadrature -- accurate to numerical noise for these smooth
    integrands well below ``n_points=96``.

    Raises ``ValueError`` if ``|displacement_m| > bead.radius_m`` (the focus
    would then sit outside the bead, outside the geometry this model
    assumes) or if the bead is not in the ray-optics regime (see
    ``ray_optics_regime``) -- a returned number there would be fiction, not
    a wrong-but-useful approximation.
    """
    if abs(displacement_m) > bead.radius_m:
        raise ValueError(
            f"|displacement_m|={abs(displacement_m):.3e} exceeds "
            f"bead.radius_m={bead.radius_m:.3e}: the focus would fall outside "
            "the bead, which this model does not cover."
        )
    regime, size_parameter = ray_optics_regime(bead, beam, medium)
    if regime != "ray_optics":
        raise ValueError(
            f"Mie size parameter x=2*pi*r/lambda_medium = {size_parameter:.2f} "
            f"puts this bead in the '{regime}' regime, not ray optics. A GOA "
            "force number here would be fiction; use Rayleigh scattering "
            "(regime='rayleigh') or GLMT (regime='intermediate') instead."
        )

    n1 = medium.n
    n2 = bead.n
    radius = bead.radius_m
    dx = displacement_m
    lambda0 = beam.wavelength_m
    power = power_w

    theta_max = beam.theta_max(medium)
    w0 = beam.beam_waist_m()

    a_min, a_max = np.pi / 2 - theta_max, np.pi / 2
    b_min, b_max = 0.0, np.pi  # symmetric in b -> 2*integral covers 2*pi

    a_nodes, a_weights = _gauss_legendre_grid(a_min, a_max, n_points)
    b_nodes, b_weights = _gauss_legendre_grid(b_min, b_max, n_points)

    a, b = np.meshgrid(a_nodes, b_nodes, indexing="ij")
    wa, wb = np.meshgrid(a_weights, b_weights, indexing="ij")

    r = np.arccos(np.cos(a) * np.cos(b))
    sin_a_inc = np.clip(dx / radius * np.sin(r), -1.0, 1.0)
    a_inc = np.arcsin(sin_a_inc)
    a_ref = np.arcsin(np.clip((n1 / n2) * np.sin(a_inc), -1.0, 1.0))

    cos_inc, cos_ref = np.cos(a_inc), np.cos(a_ref)
    Rs = np.abs((n1 * cos_inc - n2 * cos_ref) / (n1 * cos_inc + n2 * cos_ref)) ** 2
    Rp = np.abs((n1 * cos_ref - n2 * cos_inc) / (n1 * cos_ref + n2 * cos_inc)) ** 2
    R = (Rs + Rp) / 2
    T = 1 - R

    denom = 1 + R**2 + 2 * R * np.cos(2 * a_ref)
    Qs = 1 + R * np.cos(2 * a_inc) - T**2 * (
        np.cos(2 * a_inc - 2 * a_ref) + R * np.cos(2 * a_inc)
    ) / denom
    Qg = R * np.sin(2 * a_inc) - T**2 * (
        np.sin(2 * a_inc - 2 * a_ref) + R * np.sin(2 * a_inc)
    ) / denom

    k = radius * (cos_inc + (np.cos(r) / np.sin(r)) * np.sin(a_inc))
    r_laser = k * np.cos(a)
    z_laser = -k * np.sin(a)
    w = w0 * np.sqrt(1 + (lambda0 * z_laser / (np.pi * w0**2)) ** 2)
    intensity = 2 * power / (np.pi * w**2) * np.exp(-2 * (r_laser / w) ** 2)

    Qy = Qg * np.sin(r) - Qs * np.cos(r)
    Qz = Qs * np.sin(r) - Qg * np.cos(r)

    fy_integrand = intensity * Qy * n1 / C_LIGHT * k**2 * np.cos(a)
    fz_integrand = intensity * Qz * n1 / C_LIGHT * k**2 * np.cos(a)

    f_radial = 2 * np.sum(fy_integrand * wa * wb)
    f_axial = 2 * np.sum(fz_integrand * wa * wb)
    return float(f_radial), float(f_axial)


def radial_stiffness_n_per_m(
    power_w: float,
    bead: Bead,
    medium: Medium,
    beam: ObjectiveBeam,
    *,
    probe_fraction: float = 0.02,
    n_points: int = 96,
) -> float:
    """Linear-regime radial trap stiffness kappa = -dF_radial/dx at x=0.

    Central finite difference at +/- ``probe_fraction * bead.radius_m``
    (default 2% of the bead radius -- small enough to sit in the linear part
    of the force curve for the geometries this model targets, but this is a
    heuristic, not a measured convergence bound; halve it and compare if the
    force curve is unusually sharp near the origin).
    """
    probe = probe_fraction * bead.radius_m
    f_plus, _ = trap_force(power_w, probe, bead, medium, beam, n_points=n_points)
    f_minus, _ = trap_force(power_w, -probe, bead, medium, beam, n_points=n_points)
    return -(f_plus - f_minus) / (2 * probe)
