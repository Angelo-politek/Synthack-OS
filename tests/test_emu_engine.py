"""Passo 2 dell'harness: avvio completo del motore audio originale."""

import pytest

pytest.importorskip("unicorn")

import memmap  # noqa: E402

pytestmark = pytest.mark.skipif(not memmap.default_section7().exists(), reason="firmware stock assente")

import engine  # noqa: E402


@pytest.fixture(scope="module")
def booted():
    e = engine.Engine(trace_periph=True)
    e.boot()
    return e


def test_boot_handshake_sequence(booted):
    # 1 = inizio; 3..12 = handshake riuscito, voci inizializzate, interrupt installato
    assert booted.status == [1] + engine.BOOT_STEPS
    # mailbox: "B0" (risposta CPU #1), comando 3 (avvio), 0xA5A5 (conferma del motore)
    assert bytes(booted.uc.mem_read(engine.MBOX_HANDSHAKE, 6)) == b"B0\x00\x03\xa5\xa5"


def test_boot_installs_audio_isr(booted):
    assert booted.rd32(engine.VBR + 4 * engine.VECTOR_DTIM0) == engine.AUDIO_ISR


def test_boot_programs_dtim0_and_intc(booted):
    regs = booted.periph.regs
    assert regs[0xFC07_0000] == 0xC1      # DTMR0: cattura su qualsiasi fronte
    assert regs[0xFC04_801D] == 32        # CIMR0: smaschera la sorgente 32 (DTIM0)
    assert regs[0xFC04_8060] == 3         # ICR0 sorgente 32: livello 3


def test_boot_initialises_8_voices(booted):
    # 8 strutture voce da 1800 B in SRAM: dopo voice_prep/voice_reset non sono tutte zero
    for v in range(8):
        assert any(booted.uc.mem_read(0x8000_0000 + 1800 * v, 1800)), v


def test_render_block_runs_isr_with_emac_and_dma(booted):
    before = booted.emac.count
    out = booted.render_block(bytes(engine.PARAMS_SIZE))
    assert booted.emac.count > before                       # il DSP usa l'EMAC
    ch, src, dst, n = booted.periph.dma_transfers[-1]
    assert (ch, src, dst, n) == (47, 0x8000_3840, engine.AUDIO_OUT, engine.AUDIO_SIZE)
    assert len(out) == engine.VOICES and all(len(v) == engine.BLOCK for v in out)
    assert all(x == 0 for v in out for x in v)              # nessuna nota: silenzio
