# Maintainer: jpmelo031 <https://github.com/jpmelo031>
pkgname=cobra-rgb-git
_repo=cobra-rgb-linux
pkgver=0.1.0
pkgrel=1
pkgdesc="Configurador de LED pro mouse Redragon Cobra (USB 04D9:FC62)"
arch=('any')
url="https://github.com/jpmelo031/cobra-rgb-linux"
license=('unknown')
depends=('python' 'python-gobject' 'gtk4')
makedepends=('git' 'python-build' 'python-installer' 'python-setuptools' 'python-wheel')
provides=('cobra-rgb')
conflicts=('cobra-rgb')
install=cobra-rgb.install
source=("git+$url.git")
sha256sums=('SKIP')

pkgver() {
  cd "$_repo"
  printf "0.1.0.r%s.g%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

build() {
  cd "$_repo"
  python -m build --wheel --no-isolation
}

check() {
  cd "$_repo"
  python -m unittest discover -s tests
}

package() {
  cd "$_repo"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 data/70-cobra-rgb.rules "$pkgdir/usr/lib/udev/rules.d/70-cobra-rgb.rules"
  install -Dm644 data/io.github.jpmelo031.CobraRGB.desktop -t "$pkgdir/usr/share/applications"
  install -Dm644 data/io.github.jpmelo031.CobraRGB.svg -t "$pkgdir/usr/share/icons/hicolor/scalable/apps"
  install -Dm644 README.md -t "$pkgdir/usr/share/doc/$pkgname"
}
