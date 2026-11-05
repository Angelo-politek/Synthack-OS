/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef ELEKLOADER_ST_NATIVE_H
#define ELEKLOADER_ST_NATIVE_H
#include "modules.h"
/* Core-owned OS 1.41 native transactions. ST_EV_NATIVE handlers have signature
 * int f(operation, borrowed arguments, result). Nonzero supplies *result;
 * zero continues the shared collection and then the exact stock replay.
 * Arguments/results are 32-bit target words, synchronous, never retained.
 * No addresses or executable patch plans are accepted from a bank. */
/* Arguments/result by operation:
 * TRIG: six native C arguments -> prepared event pointer (IRQ/preparation).
 * ENQUEUE: event,time -> native result (sequencer IRQ).
 * IMMEDIATE: event -> consumed boolean (native exclusion already held).
 * PUBLISH: working block -> notification; leave unconsumed (MAIN IRQ).
 * TYPE: native type cursor -> effective signed type (MAIN IRQ).
 * HEADER_LOAD: destination,source -> native result; HEADER_RESET: dest,quiet.
 * SOUND/MACHINE_ALLOWED: track -> 1 allowed; consume only a refusal.
 * PAGE_SYNC/BEGIN: view,zero; END: zero,zero -> UI notifications, unconsumed.
 * A PAGE_NAV subscriber must synchronize the view as PAGE_SYNC would: the
 * per-knob navigation path sends PAGE_NAV without a second PAGE_SYNC.
 * PAGE_NAV: view,knob -> ID, ffffffff means no override.
 * PAGE_LAYOUT: page (3, and 37/38 for LFO3 actions) -> borrowed layout
 * pointer; zero means no override.
 * PAGE_GUARD: view,zero -> 1 consumes the native page mutation.
 * OWNERS: null args -> borrowed 12-byte track-owner map, or zero (MAIN IRQ).
 * Core 0.12.19: args {1} requests LFO state owners instead. Sound/configuration
 * owners remain unchanged; independent voices own their own LFO state.
 * Modules may query both through host API 8 native_query, in MAIN IRQ only.
 * MODULATION/LFO: optional replacement entry pointer; zero uses the core's
 * original prologue/continuation with the original stack arguments. MODULATION
 * args are null; LFO args are the native {working, tempo, trigs} (core 0.12.14+,
 * null before), readable by non-consuming subscribers such as LFO3.
 * Replays for TRIG/ENQUEUE/headers/layout are supplied through host API 2.
 * Header operations inherit the native task; all PAGE operations are UI-only.
 */
enum st_native_operation {
 ST_NATIVE_TRIG, ST_NATIVE_ENQUEUE, ST_NATIVE_IMMEDIATE,
 ST_NATIVE_PUBLISH, ST_NATIVE_TYPE, ST_NATIVE_HEADER_LOAD, ST_NATIVE_HEADER_RESET,
 ST_NATIVE_SOUND_ALLOWED, ST_NATIVE_MACHINE_ALLOWED,
 ST_NATIVE_PAGE_SYNC, ST_NATIVE_PAGE_NAV, ST_NATIVE_PAGE_LAYOUT,
 ST_NATIVE_PAGE_BEGIN, ST_NATIVE_PAGE_END, ST_NATIVE_PAGE_GUARD,
 ST_NATIVE_OWNERS, ST_NATIVE_MODULATION, ST_NATIVE_LFO, ST_NATIVE_OPERATION_COUNT,
 /* 18/19 remain the TYPE filter bytes, including for older bank binaries.
  * OPERATION_COUNT stays 18: host API 4 profiler buffers are 36 words. */
 ST_NATIVE_NOTE_ACCEPT=20, ST_NATIVE_SOUND_META, ST_NATIVE_OPERATION_LIMIT
};
/* Host API 8, MAIN IRQ, after track mute/staleness and Sound resolution, before
 * note gate/pitch/lock effects. args = {event, sound, effective_time, frame_end}.
 * Native time is a wrapping 32-bit musical
 * clock; quarter note = 21600000 units. frame_end is the native saved deadline.
 * All pointers are borrowed; do not free or retain an event or Sound pointer.
 * A subscriber returning nonzero supplies *result: zero replays stock, nonzero
 * skips its effects and reaches the SAME native event release. Observers return
 * zero. This is acceptance of any audio-track event, including releases/legato;
 * inspect the event's action/type/flags before interpreting it as note-on.
 * No event construction or ownership change is implied by this notification.
 */
#endif
