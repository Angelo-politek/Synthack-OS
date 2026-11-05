/* SPDX-License-Identifier: GPL-2.0-or-later
 * Borrowed OS 1.41 pattern services, UI task only. These use the existing
 * native models/proxies and the core's normal parameter-ID translation.
 * No ownership transfer, private lock matrix or firmware hook.
 */
#ifndef ELEKLOADER_ST_PATTERN_H
#define ELEKLOADER_ST_PATTERN_H
static __inline__ void *st_pattern_active_track(void *app)
{return (void *)((unsigned int (*)(void *))0x40019036u)(app);}   /* SyntHack: the OS returns pointers in d0 */
static __inline__ void *st_pattern_track_data(void *track)
{return (void *)((unsigned int (*)(void *))(*(unsigned int **)track)[0x28/4])(track);}
static __inline__ unsigned int st_pattern_track_length(void *track)
{return ((unsigned int (*)(void *))0x40027f3au)(track);}
static __inline__ int st_pattern_step_present(void *track,unsigned int step)
{
    return (unsigned char)((unsigned int (*)(void *,unsigned int))0x4002787cu)(track,step) ||
        (unsigned char)((unsigned int (*)(void *,unsigned int))0x400278d8u)(track,step);
}
static __inline__ int st_pattern_lock_get(void *view,unsigned int step,unsigned int id)
{return ((int (*)(void *,unsigned int,unsigned int))0x40037942u)(view,step,id);}
static __inline__ void st_pattern_lock_set(void *view,unsigned int step,unsigned int id,unsigned int value)
{((void (*)(void *,unsigned int,unsigned int,unsigned int))0x400387b4u)(view,step,id,value);}
static __inline__ void st_pattern_lock_clear(void *view,unsigned int step,unsigned int id)
{((void (*)(void *,unsigned int,unsigned int))0x400379a8u)(view,step,id);}
#endif
