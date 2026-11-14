// Shared header behaviour (rawtree.com web-header.tsx): blurred pill on scroll (.scrolled), full-screen menu on mobile.
const header = document.getElementById("site-header");
const menuBtn = document.getElementById("menu-btn");
const onScroll = () => header.classList.toggle("scrolled", window.scrollY > 24 && !document.body.classList.contains("menu-open"));
window.addEventListener("scroll", onScroll, { passive: true });
onScroll();
const setMenu = open => {
  document.body.classList.toggle("menu-open", open);
  menuBtn.setAttribute("aria-expanded", open);
  menuBtn.setAttribute("aria-label", open ? "Close navigation menu" : "Open navigation menu");
  onScroll();
};
menuBtn.addEventListener("click", () => setMenu(!document.body.classList.contains("menu-open")));
document.querySelectorAll("#mobile-menu a").forEach(a => a.addEventListener("click", () => setMenu(false)));
matchMedia("(min-width: 721px)").addEventListener("change", e => e.matches && setMenu(false));
