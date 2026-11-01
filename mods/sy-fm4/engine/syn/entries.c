/* The blob's entry table, at its link address (blob.ld): what the patcher
 * writes into section 7's prep and render tables. */
#include <stdint.h>
void syn_fm4_prep(int32_t, uint8_t *, uint8_t *);
void syn_fm4_render(int32_t *, uint8_t *);
__attribute__((section(".entries"), used))
void *const fm4_entries[2] = {(void *)syn_fm4_prep, (void *)syn_fm4_render};
