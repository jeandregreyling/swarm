/* ops/it8628_probe.c — read-only probe for IT8628E Super-I/O on Dell OptiPlex 7090
 *
 * Identifies the chip + reads the EC base address + dumps PWM-related EC
 * registers. Does NOT write anything. Safe to run live.
 *
 * Build: gcc -O2 -Wall -o /tmp/it8628-probe ops/it8628_probe.c
 * Run:   sudo /tmp/it8628-probe
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/io.h>
#include <unistd.h>

#define SIO_INDEX 0x4e
#define SIO_DATA  0x4f

static void sio_enter(void) {
    /* IT87xx MB Pnp Mode entry. The 4th byte differs by port:
     *   0x2e → 0x55, 0x4e → 0xaa  (matches kernel drivers/hwmon/it87.c). */
    outb(0x87, SIO_INDEX);
    outb(0x01, SIO_INDEX);
    outb(0x55, SIO_INDEX);
    outb(SIO_INDEX == 0x4e ? 0xaa : 0x55, SIO_INDEX);
}
static void sio_exit(void) {
    outb(0x02, SIO_INDEX);
    outb(0x02, SIO_DATA);
}
static uint8_t sio_read(uint8_t reg) {
    outb(reg, SIO_INDEX);
    return inb(SIO_DATA);
}
static void sio_select_ldn(uint8_t ldn) {
    outb(0x07, SIO_INDEX);
    outb(ldn,  SIO_DATA);
}

/* EC index/data pair access (base = port from LDN4 reg 0x60/0x61) */
static uint8_t ec_read(uint16_t base, uint8_t reg) {
    outb(reg, base + 5);
    return inb(base + 6);
}

int main(void) {
    if (iopl(3) < 0) { perror("iopl(3) (need root)"); return 1; }

    sio_enter();

    uint8_t chip_id_h = sio_read(0x20);
    uint8_t chip_id_l = sio_read(0x21);
    uint8_t chip_rev  = sio_read(0x22);
    uint16_t chip_id = (chip_id_h << 8) | chip_id_l;

    printf("Chip ID: 0x%04x  rev: 0x%02x\n", chip_id, chip_rev);
    if (chip_id != 0x8628) {
        printf("  (expected 0x8628 IT8628E — got something else)\n");
    }

    /* LDN 4 = Environment Controller */
    sio_select_ldn(0x04);
    uint8_t ec_en = sio_read(0x30);
    uint16_t ec_base = (sio_read(0x60) << 8) | sio_read(0x61);
    printf("LDN4 (EC): activate=0x%02x  base=0x%04x\n", ec_en, ec_base);

    sio_exit();

    if (ec_base == 0 || ec_base == 0xffff) {
        printf("EC base address invalid — aborting EC dump.\n");
        return 1;
    }

    /* Dump fan-control registers per IT8728F/IT8628E datasheet. */
    printf("\nEC fan-control registers @ base 0x%04x:\n", ec_base);
    struct { uint8_t r; const char *name; } regs[] = {
        {0x13, "FAN_CTL2 (FAN1-3 enable)"},
        {0x14, "FAN_CTL3"},
        {0x15, "FAN_TAC1_CTL"},
        {0x16, "FAN_TAC2_CTL"},
        {0x17, "FAN_TAC3_CTL"},
        {0x50, "FAN_PWM_CTL_FAN_CTL2 (smart_guardian master)"},
        {0x51, "FAN_PWM_CTL_TEMP1"},
        {0x52, "FAN_PWM_CTL_TEMP2"},
        {0x53, "FAN_PWM_CTL_TEMP3"},
        {0x60, "FAN_TAC1_LO"},
        {0x61, "FAN_TAC1_HI"},
        {0x63, "FAN1_PWM_CTL_MODE"},  /* bit7=manual; bits6:0 = duty if manual */
        {0x6B, "FAN1_PWM_DUTY (extended)"},
        {0x73, "FAN2_PWM_CTL_MODE"},
        {0x7B, "FAN2_PWM_DUTY"},
        {0x83, "FAN3_PWM_CTL_MODE"},
        {0x8B, "FAN3_PWM_DUTY"},
        {0,    NULL},
    };
    for (int i = 0; regs[i].name; i++) {
        printf("  0x%02x %-40s = 0x%02x  (%d)\n",
               regs[i].r, regs[i].name, ec_read(ec_base, regs[i].r), ec_read(ec_base, regs[i].r));
    }
    iopl(0);
    return 0;
}
