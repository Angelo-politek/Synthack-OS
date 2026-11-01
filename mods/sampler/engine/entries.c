/* The blob's entry table, at its link address: what make_patch.py writes into section 7's prep and
 * render tables for engine 11. */
#include <stdint.h>
void syn_smp_prep(int32_t, uint8_t *, uint8_t *);
void syn_smp_render(int32_t *, uint8_t *);
__attribute__((section(".entries"), used))
void *const smp_entries[2] = {(void *)syn_smp_prep, (void *)syn_smp_render};
