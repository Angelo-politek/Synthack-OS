| Task-only, bounded MAIN correction-bank/storage-lease snapshot. Single-core IRQ
| exclusion as Synfact: preserve the complete SR and restore it unchanged.
| No cache/MMU/EMAC or vector changes. No lock surrounds disk/heap/normalizing.
        .text
        .globl recorder_irq_lock,recorder_irq_unlock
        .type recorder_irq_lock,@function
recorder_irq_lock:
        moveq #0,%d0
        move.w %sr,%d0
        move.w #0x2700,%sr
        rts
        .size recorder_irq_lock,.-recorder_irq_lock
        .type recorder_irq_unlock,@function
recorder_irq_unlock:
        move.l 4(%sp),%d0
        move.w %d0,%sr
        rts
        .size recorder_irq_unlock,.-recorder_irq_unlock
