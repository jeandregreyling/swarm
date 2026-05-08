/* ops/dell_bios_fan_ctrl.c
 *
 * Tiny userspace helper for Dell laptops/desktops. Issues the SMM call
 * that tells the firmware to release fan-curve control to userspace
 * (or hand it back). This is what Dell Power Manager does on Windows;
 * `dell_smm_hwmon` in Linux does not.
 *
 * Based on the public clopez/dell-bios-fan-control reference + the
 * kernel-side i8k_smm() in drivers/hwmon/dell-smm-hwmon.c.
 *
 * Usage:
 *   dell-bios-fan-ctrl 0   # ENABLE BIOS fan control (safe default)
 *   dell-bios-fan-ctrl 1   # DISABLE BIOS fan control (userspace owns)
 *
 * Must run as root. Operates via the privileged SMM (System Management
 * Mode) interface; pwm writes only stick when BIOS control is disabled.
 *
 * Tested intent: Dell OptiPlex 7090 (Tiger Lake). Falls through several
 * SMM command variants (0x34A3, 0x35A3, 0xA3) because the magic differs
 * across BIOS versions. Returns 0 if at least one variant succeeds.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/io.h>
#include <unistd.h>
#include <errno.h>

struct smm_regs {
    unsigned int eax;
    unsigned int ebx;
    unsigned int ecx;
    unsigned int edx;
    unsigned int esi;
    unsigned int edi;
};

/* SMM I/O port pair used by Dell SMM BIOS. */
#define DELL_SMM_PORT 0xb2
#define DELL_DATA_PORT 0x84

/* Inline asm copied from kernel drivers/hwmon/dell-smm-hwmon.c::i8k_smm().
 * Triggers the SMI; BIOS handles the call inside SMM and returns. */
static int i8k_smm(struct smm_regs *regs)
{
    int rc;
    int eax = regs->eax;

#if defined(__x86_64__)
    asm volatile(
        "pushq %%rax\n\t"
        "movl 0(%%rax),%%edx\n\t"
        "pushq %%rdx\n\t"
        "movl 4(%%rax),%%ebx\n\t"
        "movl 8(%%rax),%%ecx\n\t"
        "movl 12(%%rax),%%edx\n\t"
        "movl 16(%%rax),%%esi\n\t"
        "movl 20(%%rax),%%edi\n\t"
        "popq %%rax\n\t"
        "out %%al,$0xb2\n\t"
        "out %%al,$0x84\n\t"
        "xchgq %%rax,(%%rsp)\n\t"
        "movl %%ebx,4(%%rax)\n\t"
        "movl %%ecx,8(%%rax)\n\t"
        "movl %%edx,12(%%rax)\n\t"
        "movl %%esi,16(%%rax)\n\t"
        "movl %%edi,20(%%rax)\n\t"
        "popq %%rdx\n\t"
        "movl %%edx,0(%%rax)\n\t"
        "pushfq\n\t"
        "popq %%rax\n\t"
        "andl $1,%%eax\n\t"
        : "=a"(rc)
        : "a"(regs)
        : "%ebx", "%ecx", "%edx", "%esi", "%edi", "memory"
    );
#else
#error "x86_64 only"
#endif

    if (rc != 0 || (regs->eax & 0xffff) == 0xffff || regs->eax == eax)
        return -EINVAL;
    return 0;
}

static int try_cmd(unsigned int eax, unsigned int ebx, const char *label)
{
    struct smm_regs regs;
    memset(&regs, 0, sizeof(regs));
    regs.eax = eax;
    regs.ebx = ebx;
    int r = i8k_smm(&regs);
    fprintf(stderr, "  %-12s eax=0x%08x ebx=0x%x -> rc=%d (eax_after=0x%x)\n",
            label, eax, ebx, r, regs.eax);
    return r;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s {0|1}\n  0 = ENABLE BIOS fan control\n  1 = DISABLE BIOS fan control\n", argv[0]);
        return 2;
    }
    unsigned int arg = (unsigned int) atoi(argv[1]) ? 1 : 0;

    if (iopl(3) < 0) {
        perror("iopl(3) (need root + CAP_SYS_RAWIO)");
        return 1;
    }

    fprintf(stderr, "Issuing Dell SMM disable_bios_fan_ctrl=%u — trying known variants:\n", arg);

    int ok = 0;
    /* Modern OptiPlex / Latitude / XPS BIOS revisions. */
    if (try_cmd(0x34A3, arg, "0x34A3") == 0) ok++;
    /* Some firmware exposes 0x35A3 instead. */
    if (try_cmd(0x35A3, arg, "0x35A3") == 0) ok++;
    /* Legacy laptops (e.g. Latitude E-series). */
    if (try_cmd(0xA3,   arg, "0xA3"  ) == 0) ok++;

    iopl(0);

    if (ok == 0) {
        fprintf(stderr, "ALL VARIANTS FAILED — BIOS does not expose the disable hook on this model.\n");
        return 1;
    }
    fprintf(stderr, "OK — %d variant(s) acknowledged. pwm writes should now stick.\n", ok);
    return 0;
}
