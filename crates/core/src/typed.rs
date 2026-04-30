use serde::{Deserialize, Serialize};
use std::fmt;
use std::ops::{Add, AddAssign, Div, Mul, Sub, SubAssign};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct CycleCount(pub u64);

impl CycleCount {
    pub const ZERO: Self = Self(0);
    pub fn new(n: u64) -> Self {
        Self(n)
    }
    pub fn get(self) -> u64 {
        self.0
    }
    pub fn checked_add(self, rhs: Self) -> Option<Self> {
        self.0.checked_add(rhs.0).map(Self)
    }
    pub fn saturating_sub(self, rhs: Self) -> Self {
        Self(self.0.saturating_sub(rhs.0))
    }
    pub fn saturating_add(self, rhs: Self) -> Self {
        Self(self.0.saturating_add(rhs.0))
    }
}

impl fmt::Display for CycleCount {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl Add for CycleCount {
    type Output = Self;
    fn add(self, rhs: Self) -> Self {
        Self(self.0.wrapping_add(rhs.0))
    }
}

impl Sub for CycleCount {
    type Output = Self;
    fn sub(self, rhs: Self) -> Self {
        Self(self.0.wrapping_sub(rhs.0))
    }
}

impl AddAssign for CycleCount {
    fn add_assign(&mut self, rhs: Self) {
        self.0 = self.0.wrapping_add(rhs.0);
    }
}

impl SubAssign for CycleCount {
    fn sub_assign(&mut self, rhs: Self) {
        self.0 = self.0.wrapping_sub(rhs.0);
    }
}

impl Mul<u64> for CycleCount {
    type Output = Self;
    fn mul(self, rhs: u64) -> Self {
        Self(self.0.wrapping_mul(rhs))
    }
}

impl Div<u64> for CycleCount {
    type Output = Self;
    fn div(self, rhs: u64) -> Self {
        Self(self.0 / rhs)
    }
}

impl From<u64> for CycleCount {
    fn from(n: u64) -> Self {
        Self(n)
    }
}

impl From<CycleCount> for u64 {
    fn from(c: CycleCount) -> Self {
        c.0
    }
}

impl CycleCount {
    /// Saturating multiplication by a scalar — clamps at u64::MAX.
    pub fn saturating_mul(self, rhs: u64) -> Self {
        Self(self.0.saturating_mul(rhs))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct CoreId(pub u32);

impl CoreId {
    pub fn new(id: u32) -> Self {
        Self(id)
    }
    pub fn get(self) -> u32 {
        self.0
    }
}

impl fmt::Display for CoreId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl From<u32> for CoreId {
    fn from(id: u32) -> Self {
        Self(id)
    }
}

impl From<CoreId> for u32 {
    fn from(c: CoreId) -> Self {
        c.0
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct EventTypeId(pub u32);

impl EventTypeId {
    pub fn new(id: u32) -> Self {
        Self(id)
    }
    pub fn get(self) -> u32 {
        self.0
    }
}

impl fmt::Display for EventTypeId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl From<u32> for EventTypeId {
    fn from(id: u32) -> Self {
        Self(id)
    }
}

impl From<EventTypeId> for u32 {
    fn from(e: EventTypeId) -> Self {
        e.0
    }
}

/// Memory address newtype with checked arithmetic for safe offset ops.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct MemAddr(pub u64);

impl MemAddr {
    pub fn new(addr: u64) -> Self {
        Self(addr)
    }
    pub fn get(self) -> u64 {
        self.0
    }
    /// Offset from a base address (saturating — never wraps).
    pub fn offset_from(self, base: Self) -> u64 {
        self.0.saturating_sub(base.0)
    }
    /// Checked addition of a raw byte offset.
    pub fn checked_add(self, offset: u64) -> Option<Self> {
        self.0.checked_add(offset).map(Self)
    }
}

impl fmt::Display for MemAddr {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "0x{:016x}", self.0)
    }
}

/// Trace identifier newtype — unique handle for a loaded trace session.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct TraceId(pub u64);

impl TraceId {
    pub fn new(id: u64) -> Self {
        Self(id)
    }
    pub fn get(self) -> u64 {
        self.0
    }
}

impl fmt::Display for TraceId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── CycleCount arithmetic ────────────────────────────────────────

    #[test]
    fn add_two_cycle_counts() {
        let a = CycleCount::new(100);
        let b = CycleCount::new(50);
        assert_eq!(a + b, CycleCount::new(150));
    }

    #[test]
    fn sub_two_cycle_counts() {
        let a = CycleCount::new(100);
        let b = CycleCount::new(30);
        assert_eq!(a - b, CycleCount::new(70));
    }

    #[test]
    fn add_assign_cycle_count() {
        let mut a = CycleCount::new(10);
        a += CycleCount::new(5);
        assert_eq!(a, CycleCount::new(15));
    }

    #[test]
    fn sub_assign_cycle_count() {
        let mut a = CycleCount::new(10);
        a -= CycleCount::new(3);
        assert_eq!(a, CycleCount::new(7));
    }

    #[test]
    fn mul_cycle_count_by_scalar() {
        let c = CycleCount::new(8);
        assert_eq!(c * 4, CycleCount::new(32));
    }

    #[test]
    fn div_cycle_count_by_scalar() {
        let c = CycleCount::new(100);
        assert_eq!(c / 4, CycleCount::new(25));
    }

    // ── Overflow behaviour ───────────────────────────────────────────

    #[test]
    fn add_wraps_on_overflow() {
        let a = CycleCount::new(u64::MAX);
        let b = CycleCount::new(1);
        assert_eq!(a + b, CycleCount::new(0));
    }

    #[test]
    fn sub_wraps_on_underflow() {
        let a = CycleCount::new(0);
        let b = CycleCount::new(1);
        assert_eq!(a - b, CycleCount::new(u64::MAX));
    }

    #[test]
    fn mul_wraps_on_overflow() {
        let c = CycleCount::new(u64::MAX);
        assert_eq!(c * 2, CycleCount::new(u64::MAX.wrapping_mul(2)));
    }

    #[test]
    fn saturating_mul_clamps_at_max() {
        let c = CycleCount::new(u64::MAX);
        assert_eq!(c.saturating_mul(2), CycleCount::new(u64::MAX));
    }

    #[test]
    fn saturating_add_clamps_at_max() {
        let a = CycleCount::new(u64::MAX);
        assert_eq!(
            a.saturating_add(CycleCount::new(1)),
            CycleCount::new(u64::MAX)
        );
    }

    #[test]
    fn saturating_sub_clamps_at_zero() {
        let a = CycleCount::new(5);
        assert_eq!(a.saturating_sub(CycleCount::new(100)), CycleCount::ZERO);
    }

    // ── From conversions ─────────────────────────────────────────────

    #[test]
    fn cycle_count_from_u64() {
        let c: CycleCount = 42u64.into();
        assert_eq!(c, CycleCount::new(42));
    }

    #[test]
    fn u64_from_cycle_count() {
        let c = CycleCount::new(99);
        let n: u64 = c.into();
        assert_eq!(n, 99);
    }

    #[test]
    fn core_id_from_u32() {
        let c: CoreId = 7u32.into();
        assert_eq!(c, CoreId::new(7));
    }

    #[test]
    fn u32_from_core_id() {
        let c = CoreId::new(3);
        let n: u32 = c.into();
        assert_eq!(n, 3);
    }

    #[test]
    fn event_type_id_from_u32() {
        let e: EventTypeId = 5u32.into();
        assert_eq!(e, EventTypeId::new(5));
    }

    #[test]
    fn u32_from_event_type_id() {
        let e = EventTypeId::new(11);
        let n: u32 = e.into();
        assert_eq!(n, 11);
    }

    // ── Display formatting ───────────────────────────────────────────

    #[test]
    fn display_cycle_count() {
        assert_eq!(format!("{}", CycleCount::new(1024)), "1024");
    }

    #[test]
    fn display_core_id() {
        assert_eq!(format!("{}", CoreId::new(0)), "0");
    }

    #[test]
    fn display_event_type_id() {
        assert_eq!(format!("{}", EventTypeId::new(3)), "3");
    }

    #[test]
    fn display_mem_addr_hex() {
        assert_eq!(format!("{}", MemAddr::new(0x1000)), "0x0000000000001000");
    }

    // ── ZERO constant ────────────────────────────────────────────────

    #[test]
    fn cycle_count_zero_identity() {
        let c = CycleCount::new(50);
        assert_eq!(c + CycleCount::ZERO, c);
        assert_eq!(c - CycleCount::ZERO, c);
    }
}
