/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SYNFACT_ST_ARP_RUNTIME_H
#define SYNFACT_ST_ARP_RUNTIME_H
#include "clock.h"
/* All calls run in the MAIN IRQ/native exclusion. copy is the native event
 * copy operation (retains lock refs); alloc/free use its bounded event pool. */
struct arp_runtime_api {
    arp_u32 *(*alloc)(void);
    void (*copy)(arp_u32 *,const arp_u32 *);
    void (*free)(arp_u32 *);
    int (*queue)(arp_u32 *,arp_u32 time);
};
struct arp_runtime {
    struct arp_selector selector;
    struct arp_clock clock;
    arp_u32 *source;
    arp_u32 generation,until,finite,track,emitted,dropped;
    /* Output kind: 1 (sequencer) for a sequence root, 2 (live) for held keys.
     * The native stale test (400a4236) drops an event whose kind is below the
     * track's last started note (45510fc8, set at 400a435a): kind 2 outputs
     * hid every following sequencer trig, its p-locks included. Queued
     * outputs are remembered so the root adapter never recaptures them. */
    arp_u32 kind,*queued[8],queued_note[8],queued_generation[8];unsigned int queued_next;
    const struct arp_runtime_api *api;
    /* Flat native Sound record, captured before the mutable UI preview can
     * select another track. Outputs are due in their current MAIN frame. */
    unsigned char live_sound[0x123];
};
void arp_runtime_init(struct arp_runtime *,const struct arp_runtime_api *);
void arp_runtime_stop(struct arp_runtime *);
/* Start a sequence-note chord from an accepted event. Returns nonzero only
 * after retaining a template successfully. Caller still owns original event.
 * Accepts audio-track sequence notes, no pooled Sound ptr.
 * chord = optional signed semitone offsets, max 3; zero means absent.
 * Output gate is computed from the current LEN setting at emission time.
 */
int arp_runtime_start(struct arp_runtime *,const struct arp_settings *,
                      const arp_u32 *event,arp_u32 when,arp_u32 generation,
                      const int *chord,unsigned int count);
/* Standalone monophonic live input. The native held-note set supplies the
 * chord separately; this retains only the template/Sound/lock reference. */
int arp_runtime_live_start(struct arp_runtime *,const struct arp_settings *,
                           const arp_u32 *,arp_u32 when,arp_u32 generation);
/* Output word 3 is the root's native kind: 1 for a sequence root, 2 for
 * live input. The sequence-root adapter captures kind 1, except this runtime's
 * own queued outputs (arp_runtime_owns).
 */
int arp_runtime_frame(struct arp_runtime *,const struct arp_settings *,
                      arp_u32 begin,arp_u32 end,arp_u32 generation);
/* Once, for an event this runtime queued (the same pointer and note): 1 if
 * it is from the current root, 2 if a newer root has replaced it since. */
int arp_runtime_owns(struct arp_runtime *,const arp_u32 *event);
#endif
