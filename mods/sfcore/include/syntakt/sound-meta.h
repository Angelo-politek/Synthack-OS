/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef ELEKLOADER_ST_SOUND_META_H
#define ELEKLOADER_ST_SOUND_META_H
#include "native.h"
/* API 10 task-side lifecycle notifications on the existing native bus.
 * args={kind,a,b,n}, observers return zero, ownership never transfers.
 * COPY/RELOCATE: destination,source,bytes (after native copy).
 * NEW/FREE: object/begin,zero,object/allocation bytes.
 * CODEC: destination,source,known full project container or zero.
 * S1_SAVE: native record,512-byte output scratch,known source container or zero.
 * S1_LOAD: native record,512-byte input scratch,success.
 * PROJECT_NEW/READY: known native project container,zero,zero.
 * KIT_RECORD_COPY/RECORD_COPY: destination,source,known source container or
 * zero; after native copies of 1600h / 107h bytes respectively.
 * RECORD_BIND: destination,copied byte count,known destination container;
 * publishes the copied metadata into that container's Sound carrier.
 * Firmware sites remain shared with the established object/codec adapter.
 */
enum st_sound_meta_kind {
 ST_SOUND_COPY=1,ST_SOUND_NEW,ST_SOUND_FREE,ST_SOUND_RELOCATE,
 ST_SOUND_KIT_ENCODE,ST_SOUND_KIT_DECODE,ST_SOUND_ENCODE,ST_SOUND_DECODE,
 ST_SOUND_S1_SAVE,ST_SOUND_S1_LOAD,ST_SOUND_PROJECT_NEW,ST_SOUND_PROJECT_READY,
 ST_SOUND_KIT_RECORD_COPY,ST_SOUND_RECORD_COPY,ST_SOUND_RECORD_BIND
};
#define ST_SOUND_S1_EXTENSION 0x11fu
#define ST_SOUND_S1_EXTENSION_BYTES 32u
#define ST_SOUND_S1_BYTES (ST_SOUND_S1_EXTENSION+ST_SOUND_S1_EXTENSION_BYTES)
#endif
