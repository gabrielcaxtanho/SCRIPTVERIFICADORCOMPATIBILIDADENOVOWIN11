#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificador de Compatibilidade com Windows 11 + Simulação Visual
Autor: Gabriel Vieira
Versão: 3.0 (Totalmente Integrado)
"""

import os
import sys
import socket
import platform
import getpass
import psutil
import subprocess
import json
import ctypes
import traceback
import time
import threading
import random

try:
    import wmi
except Exception:
    wmi = None

# ------------------------ Elevação de Privilégios ------------------------
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    print("🔒 Este script requer privilégios de administrador. Solicitando elevação...")
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit()

# ------------------------ Funções Auxiliares ------------------------
def safe_run(cmd, timeout=8):
    try:
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, timeout=timeout, universal_newlines=True)
        out = completed.stdout.strip()
        err = completed.stderr.strip()
        if completed.returncode == 0:
            return True, out
        else:
            return False, out if out else err
    except Exception as e:
        return False, str(e)

def bytes_to_gb(b):
    try:
        return round(b / (1024 ** 3), 2)
    except Exception:
        return None

def check_requirement(condition):
    return "✔️ Compatível" if condition else "❌ Não compatível"

# ------------------------ Coleta de Dados ------------------------
def get_hostname():
    return socket.gethostname()

def get_current_user():
    try:
        return getpass.getuser()
    except:
        return os.environ.get("USERNAME", "Desconhecido")

def get_os_info():
    ver = platform.win32_ver()
    name = platform.system()
    release = platform.release()
    version = platform.version()
    arch = platform.architecture()[0]
    return f"{name} {release} {ver[0]} ({version})", arch

def get_manufacturer_model():
    try:
        if wmi:
            c = wmi.WMI()
            for sysinfo in c.Win32_ComputerSystem():
                manu = getattr(sysinfo, "Manufacturer", "Desconhecido")
                model = getattr(sysinfo, "Model", "Desconhecido")
                return manu, model
    except:
        pass
    return "Desconhecido", "Desconhecido"

def get_cpu_info():
    try:
        if wmi:
            c = wmi.WMI()
            for cpu in c.Win32_Processor():
                name = cpu.Name.strip()
                cores = cpu.NumberOfCores
                return name, cores
    except:
        pass
    return platform.processor(), psutil.cpu_count(logical=False)

def get_ram_gb():
    return bytes_to_gb(psutil.virtual_memory().total)

def get_disk_info():
    try:
        usage = psutil.disk_usage("C:\\")
        return bytes_to_gb(usage.total), bytes_to_gb(usage.free)
    except:
        return "Desconhecido", "Desconhecido"

def get_gpu_names():
    try:
        if wmi:
            c = wmi.WMI()
            names = [g.Name.strip() for g in c.Win32_VideoController()]
            return ", ".join(names) if names else "Desconhecido"
    except:
        pass
    return "Desconhecido"

def get_tpm_info():
    ok, out = safe_run('powershell -Command "Get-Tpm | ConvertTo-Json -Depth 4"')
    if ok and out:
        try:
            j = json.loads(out)
            tpm_present = j.get("TpmPresent", False)
            tpm_enabled = j.get("TpmEnabled", False)
            tpm_ready = j.get("TpmReady", False)
            spec_ver = (j.get("SpecVersion") or "").strip("\x00")
            manuf_ver = (j.get("ManufacturerVersionFull20") or "").strip("\x00")
            manuf = (j.get("ManufacturerIdTxt") or "").strip("\x00")
            is_tpm20 = bool(manuf_ver or "Full20" in out or "2.0" in spec_ver)
            return {
                "status": "Presente" if tpm_present else "Ausente",
                "enabled": "Ativado" if tpm_enabled or tpm_ready else "Desativado",
                "version": manuf_ver or spec_ver or "Desconhecido",
                "manufacturer": manuf or "Desconhecido",
                "is_tpm20": is_tpm20,
                "raw": j
            }
        except Exception:
            pass
    return {"status": "Desconhecido", "enabled": "Desconhecido", "version": "Desconhecido", "manufacturer": "Desconhecido", "is_tpm20": False, "raw": out}

def get_secure_boot_status():
    ok, out = safe_run('powershell -Command "Confirm-SecureBootUEFI"')
    if ok and out.lower() in ("true", "false"):
        return out.title()
    return "Indisponível"

def get_firmware_type():
    # Método confiável: PowerShell CIM, fallback WMI e pastas EFI
    try:
        ok, out = safe_run('powershell -Command "(Get-CimInstance -ClassName Win32_ComputerSystem).SystemFirmwareType"')
        if ok and out.strip() in ("2", "UEFI", "uefi"): return "UEFI"
        elif ok and out.strip() in ("1", "BIOS", "bios"): return "Legacy/BIOS"
        ok, out = safe_run('powershell -Command "(Get-WmiObject -Class Win32_ComputerSystem).SystemFirmwareType"')
        if ok and out.strip() in ("2", "UEFI", "uefi"): return "UEFI"
        elif ok and out.strip() in ("1", "BIOS", "bios"): return "Legacy/BIOS"
        # Pastas EFI
        efi_paths = ["C:\\EFI", "C:\\Boot\\EFI", "C:\\Windows\\Boot\\EFI"]
        if any(os.path.exists(p) for p in efi_paths): return "UEFI"
    except Exception: pass
    return "Desconhecido"

# ------------------------ Montagem do Relatório ------------------------
def build_report(debug=False):
    host = get_hostname()
    user = get_current_user()
    os_info, arch = get_os_info()
    manu, model = get_manufacturer_model()
    cpu_name, cpu_cores = get_cpu_info()
    ram_gb = get_ram_gb()
    disk_total, disk_free = get_disk_info()
    gpu = get_gpu_names()
    tpm = get_tpm_info()
    secure_boot = get_secure_boot_status()
    firmware = get_firmware_type()

    checks = {
        "RAM": ram_gb >= 4,
        "CPU": cpu_cores >= 2,
        "Disco": isinstance(disk_total, (int, float)) and disk_total >= 64,
        "TPM": tpm["is_tpm20"] and "Ativado" in tpm["enabled"],
        "Firmware": "UEFI" in firmware,
        "SecureBoot": secure_boot.lower() == "true",
        "Arquitetura": "64" in arch
    }
    fully_compatible = all(checks.values())

    lines = ["Relatório de Compatibilidade com Windows 11 + Simulação Visual\n"]
    lines += [
        "1. Dados de Identificação e Sistema:\n",
        f"- Nome da Máquina: {host}",
        f"- Usuário Logado: {user}",
        f"- Sistema Operacional: {os_info}",
        f"- Arquitetura do SO: {arch} — {check_requirement('64' in arch)}",
        f"- Fabricante: {manu}",
        f"- Modelo: {model}\n"
    ]
    lines += [
        "2. Hardware:\n",
        f"- Memória RAM: {ram_gb} GB — {check_requirement(ram_gb >= 4)} (≥ 4 GB)",
        f"- CPU: {cpu_name} ({cpu_cores} núcleos) — {check_requirement(cpu_cores >= 2)}"
    ]
    if isinstance(disk_total, (int, float)):
        lines.append(f"- Disco C: {disk_total} GB — {check_requirement(disk_total >= 64)} (≥ 64 GB)")
    lines.append(f"- GPU: {gpu} — {check_requirement(gpu != 'Desconhecido')}\n")
    lines += [
        "3. Segurança e Firmware:\n",
        f"- TPM: {tpm['status']} / {tpm['enabled']} — {check_requirement('Ativado' in tpm['enabled'])}",
        f"- Versão TPM: {tpm['version']} — {check_requirement(tpm['is_tpm20'])} (Requisito: 2.0)",
        f"- Firmware: {firmware} — {check_requirement('UEFI' in firmware)} (Requisito: UEFI)",
        f"- Secure Boot: {secure_boot} — {check_requirement(secure_boot.lower() == 'true')} (Requisito: Ativado)\n"
    ]
    lines.append("Resumo Geral:")
    if fully_compatible:
        lines.append("✅ Este computador é TOTALMENTE compatível com o Windows 11.")
    else:
        lines.append("⚠️ Este computador NÃO atende a todos os requisitos do Windows 11.")
        faltando = [k for k, ok in checks.items() if not ok]
        lines.append("Itens não compatíveis: " + ", ".join(faltando))
    if debug:
        lines.append("\n[DEBUG] TPM RAW:")
        lines.append(str(tpm.get("raw")))
    return "\n".join(lines), host

# ------------------------ Escrita de Arquivo ------------------------
def write_output_file(content, hostname):
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
    out_path = os.path.join(base_dir, f"{hostname}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path

# ------------------------ Beep e Animações ------------------------
def do_beep(times=1, freq=1000, duration=200):
    if sys.platform.startswith("win"):
        try:
            import winsound
            for _ in range(times):
                winsound.Beep(freq, duration)
                time.sleep(0.08)
            return
        except Exception:
            pass
    for _ in range(times):
        sys.stdout.write('\a'); sys.stdout.flush(); time.sleep(0.08)

def animacao_carregamento():
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*"
    largura = 60
    while not stop_animation:
        linha = "".join(random.choice(chars) for _ in range(largura))
        print("\033[92m" + linha + "\033[0m", end="\r")
        time.sleep(0.05)

def varredura():
    for i in range(1,6):
        time.sleep(1)
        print(f"\nVerificação etapa {i}/5 concluída...")
    time.sleep(1)
    print("\n✅ Varredura finalizada com sucesso!")
    print("\n✅ Informações do sistema capturadas!")
    print("\n✅ Análise concluída de compatibilidade de SO!")

def simulacao_dir(duration_seconds=5):
    caminhos = [
        "C:\\Windows\\System32\\config\\systemprofile\\AppData\\Local",
        "C:\\Program Files\\Common Files\\microsoft shared\\Office16\\",
        "C:\\Users\\Public\\Documents\\logs\\cache.tmp",
        "C:\\Windows\\Prefetch\\CMD.EXE-34AD19B5.pf",
        "C:\\Users\\Miguel\\Downloads\\report_data.txt",
        "C:\\Users\\Miguel\\AppData\\Local\\Temp\\tmp123.tmp",
        "C:\\Program Files\\Git\\bin\\git.exe"
    ]
    inicio = time.time()
    print("\n[Iniciando listagem de arquivos... (simulação)]\n")
    while time.time() - inicio < duration_seconds:
        pasta = random.choice(caminhos)
        arquivo = random.choice(["logs.log","cache.tmp","dump.bin","config.json","readme.txt","data.db"])
        tamanho = f"{random.randint(1,2048)} KB"
        print(f"{pasta}\\{arquivo}    {tamanho}")
        time.sleep(random.uniform(0.05,0.18))
    print("\n[Simulação de listagem finalizada]\n")
    time.sleep(0.4)

def animacao_logo_final():
    os.system('cls' if os.name=='nt' else 'clear')
    logo = [
        "           ███",
        "           ███",
        "           ███",
        "      █████████████",
        "      ███       ███",
        "      ███       ███",
        "      ███       ███"
    ]
    time.sleep(2)
    for i in range(len(logo)):
        for j in range(i+1):
            print("\033[93m"+logo[j]+"\033[0m")
        for k in range(i+1,len(logo)):
            print()
        time.sleep(0.25)
        if i != len(logo)-1: print(f"\033[{len(logo)}A", end="")
    time.sleep(0.8)
    print("\n\033[92mScript finalizado com sucesso!\033[0m\n")
    print("\033[93mInformações salvas!\033[0m\n")
    do_beep(times=2, freq=1000, duration=200)

# -------------------- Execução Principal --------------------
if __name__ == "__main__":
    stop_animation = False
    loader_thread = threading.Thread(target=animacao_carregamento, daemon=True)
    loader_thread.start()

    try:
        # Varredura com pequenas pausas e print garantido
        for i in range(1, 6):
            time.sleep(1)
            print(f"\nVerificação etapa {i}/5 concluída...")
        time.sleep(1)
        print("\n✅ Varredura finalizada com sucesso!")
        print("✅ Informações do sistema capturadas!")
        print("✅ Análise concluída de compatibilidade de SO!")

        # Para a animação
        stop_animation = True
        loader_thread.join(timeout=1)

        # Simulação de diretórios
        simulacao_dir(duration_seconds=5)

        # Gerar relatório
        report, host = build_report(debug="--debug" in sys.argv)
        path = write_output_file(report, host)
        print(f"[✅] Relatório gerado com sucesso: {path}")

        # Logo final
        animacao_logo_final()

        # Pausa final obrigando o usuário a apertar ENTER
        try:
            input("Pressione ENTER para sair...")
        except EOFError:
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        stop_animation = True
        print("\nInterrompido pelo usuário.")
    except Exception:
        stop_animation = True
        print("[ERRO FATAL]\n", traceback.format_exc())
