/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CORE_ST_CRC_H
#define CORE_ST_CRC_H
/* Raw reflected CRC32 register; caller retains initial/final XOR semantics. */
unsigned int core_crc_update(unsigned int,const unsigned char *,unsigned int);
#endif
