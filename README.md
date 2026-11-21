# Cobra RGB (Linux)

Configurador leve do LED do mouse **Redragon King Cobra** (USB `04D9:FC62`) pra Linux, feito pensando no Arch.
O software oficial só existe pra Windows (e é ruim); este faz o principal sem ele.

- Cor, modo, brilho e velocidade do LED, por perfil
- Grava na memória do mouse, então vale mesmo com o programa fechado
- Mostra perfil ativo, polling e DPI (só leitura, não mexe neles)
- Interface GTK4 e linha de comando
- Backup automático das cores que estavam no mouse antes da primeira mudança

## Instalar no Arch

```bash
git clone https://github.com/jpmelo031/cobra-rgb-linux.git
cd cobra-rgb-linux
makepkg -si
```

O pacote instala uma regra do udev que deixa o usuário logado acessar o mouse sem root.
Se depois de instalar aparecer erro de permissão, tira e pluga o mouse de novo.

## Usar

Abre o **Cobra RGB** no menu de aplicativos, ou pelo terminal:

```bash
cobra-rgb                                          # abre a interface
cobra-rgb status                                   # perfil, polling, DPI e o LED de cada perfil
cobra-rgb aplicar --cor 8c00ff --modo fixo --brilho 3
cobra-rgb aplicar --modo onda --velocidade 6       # o que você não passar continua como está
cobra-rgb aplicar --perfil 2 --cor 00ff00
cobra-rgb modos                                    # lista os modos
cobra-rgb testar                                   # pisca vermelho, verde, azul e branco e volta
cobra-rgb restaurar                                # grava de volta as cores do backup
```

Modos: `fixo`, `respirando`, `piscando`, `arco-iris`, `respirando-arco-iris`, `onda`, `reativo`,
`reativo-botao`, `aleatorio`, `alternado`, `desligado`. Brilho vai de 1 a 3, velocidade de 1 a 8.

Só o perfil ativo muda o LED na hora. Os outros ficam salvos e aparecem quando você troca de perfil no mouse.

Arquivos:

- backup das cores originais: `~/.local/share/cobra-rgb/backup-original.txt`
- config: `~/.config/cobra-rgb/config` (`ordem=RGB`; só muda se o `testar` mostrar cores trocadas)

## Outras distros

Precisa de Python 3.10+; a interface precisa de GTK4 e PyGObject.

```bash
pipx install --system-site-packages .
sudo install -Dm644 data/70-cobra-rgb.rules /usr/lib/udev/rules.d/70-cobra-rgb.rules
sudo udevadm control --reload && sudo udevadm trigger
```

## Como funciona

O mouse tem uma interface USB de configuração (usage page `0xFFA0`) que recebe feature reports de 16 bytes.
No Linux ela aparece como um `/dev/hidraw*`, e o programa fala com ela por `ioctl` (`HIDIOCSFEATURE`/`HIDIOCGFEATURE`),
sem nenhuma dependência.

| Comando | O que faz |
|---|---|
| `02 f5 00` / `02 f5 01` | abre / fecha a sessão de config |
| `02 f2 <addr> <len>` | lê até 8 bytes (a resposta vem no GET feature, do byte 8 em diante) |
| `02 f3 <addr> <len> 00 00 00 <dados>` | grava até 8 bytes |
| `02 f1 02 <seção>` | recarrega uma seção |

O LED de cada perfil fica em `0x0449 + 8 × perfil`: `R G B modoA velocidade modoB brilho`.

Pegadinha: gravar o LED só muda a memória, a cor acesa não troca. Ela só troca depois da mesma sequência que o
software oficial manda ao selecionar um perfil (`02 f3 2c 00 02 … <perfil>` e `02 f1 02` com `01 08 04 02 08`),
enviada fora da sessão.

O protocolo veio do [mouse_m908](https://github.com/dokutan/mouse_m908), que mapeou vários Redragon com chip Holtek.
O Cobra M711 clássico (`04D9:FC30`) usa o mesmo protocolo e é reconhecido, mas não foi testado.

## Testes

```bash
python -m unittest discover -s tests
```

Os testes usam um mouse simulado (com a memória lida de um King Cobra de verdade) e um GTK simulado, então rodam
em qualquer máquina, sem o mouse.

## Estado

- O protocolo foi testado primeiro num King Cobra de verdade pela versão Windows do Cobra RGB, que manda os mesmos comandos.
- Testado no Linux com um King Cobra (`04D9:FC62`) no Arch com Hyprland (Wayland): instalação com `makepkg -si`,
  acesso ao hidraw sem root pela regra do udev, `status`, `aplicar` e a interface GTK4. O LED troca na hora.
- O Cobra M711 clássico (`04D9:FC30`) ainda não foi testado. Se algo der errado, abre uma issue com a saída de
  `cobra-rgb status`.
