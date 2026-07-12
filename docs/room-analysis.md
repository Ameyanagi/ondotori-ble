# Room-capture analysis

## Privacy boundary

The original capture is kept only under the Git-ignored `local/captures/`
directory. Printed serials, CoreBluetooth identifiers, device names, exact raw
packets, and firmware metadata are intentionally absent from tracked files and
package distributions.

The public parser fixture at `tests/fixtures/observed-c3-synthetic.json` is a
synthetic packet constructed to exercise the independently observed byte
pattern. It is not represented as an authentic over-the-air packet.

## Sanitized result

Targeted scans observed one T&D advertiser. The reported room inventory was
`505B`, `507`, and `502`, but the printed label of the transmitting unit and the
RTR505B input module were not recorded alongside the packet. The third serial
byte was `C3`, and two 16-bit candidate words changed consistently across
observations.

That context is useful for planning another capture, but it does not prove that
every `C3` serial is an RTR505B or identify a physical conversion. The parser
therefore exposes the family and bytes without assigning a model or readings.

## Other reported units

If `502` and `507` mean legacy RTR-502 and RTR-507 without a trailing `B`, they
do not provide this BLE transport. If either label actually ends in `B`, its BLE
state, registration, battery, and range need to be checked before drawing a
protocol conclusion.

The library will not add 429 MHz radio, optical, or base-unit transports. Only
BLE advertisements are in scope.

## Required follow-up capture

Before adding an RTR500B decoder:

1. photograph or transcribe the exact logger and input-module labels;
2. record firmware and configuration mode;
3. record the on-device or trusted reference value at the same time;
4. collect repeated advertisements while the input changes;
5. test invalid/disconnected sensor behavior; and
6. sanitize identifiers before committing fixtures.

No restricted T&D document should be placed in the repository.
