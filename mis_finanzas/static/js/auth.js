/* Mis Finanzas — comportamiento de las pantallas de acceso y seguridad.
 * Las validaciones de este archivo son sólo de ayuda visual: todas las reglas
 * importantes se vuelven a comprobar en el servidor (Python).
 */
(function () {
  "use strict";

  const MIN_PASSWORD = 10;

  /* ---------------------------------------------------------------------
   * Mostrar / ocultar contraseña
   * ------------------------------------------------------------------- */
  document.querySelectorAll("[data-toggle-password]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      const campo = document.getElementById(boton.dataset.togglePassword);
      if (!campo) return;
      const visible = campo.type === "password";
      campo.type = visible ? "text" : "password";
      boton.classList.toggle("visible", visible);
      boton.setAttribute("aria-label", visible ? "Ocultar contraseña" : "Mostrar contraseña");
      campo.focus();
    });
  });

  /* ---------------------------------------------------------------------
   * Indicador de fortaleza de contraseña
   * ------------------------------------------------------------------- */
  function evaluarFortaleza(valor, usuario) {
    if (!valor) return { nivel: 0, texto: "Mínimo " + MIN_PASSWORD + " caracteres." };
    if (usuario && valor.trim().toLowerCase() === usuario.trim().toLowerCase()) {
      return { nivel: 1, texto: "La contraseña no puede ser igual al usuario." };
    }
    if (valor.length < MIN_PASSWORD) {
      return { nivel: 1, texto: "Muy corta: faltan " + (MIN_PASSWORD - valor.length) + " caracteres." };
    }
    let puntos = 0;
    if (/[a-z]/.test(valor)) puntos++;
    if (/[A-Z]/.test(valor)) puntos++;
    if (/\d/.test(valor)) puntos++;
    if (/[^A-Za-z0-9]/.test(valor)) puntos++;
    if (valor.length >= 14) puntos++;
    if (valor.length >= 20) puntos++;
    if (puntos <= 2) return { nivel: 2, texto: "Aceptable. Combina mayúsculas, números y símbolos." };
    if (puntos <= 4) return { nivel: 3, texto: "Buena contraseña." };
    return { nivel: 4, texto: "Contraseña muy segura." };
  }

  document.querySelectorAll("[data-medidor]").forEach(function (campo) {
    const medidor = document.getElementById("medidor-" + campo.dataset.medidor);
    if (!medidor) return;
    const texto = medidor.querySelector(".medidor-texto");
    const campoUsuario = campo.form ? campo.form.querySelector('input[name="usuario"]') : null;
    const actualizar = function () {
      const r = evaluarFortaleza(campo.value, campoUsuario ? campoUsuario.value : "");
      medidor.dataset.nivel = String(r.nivel);
      if (texto) texto.textContent = r.texto;
    };
    campo.addEventListener("input", actualizar);
    if (campoUsuario) campoUsuario.addEventListener("input", actualizar);
  });

  /* ---------------------------------------------------------------------
   * Validación básica de formularios (el servidor valida de nuevo)
   * ------------------------------------------------------------------- */
  function marcarError(campo, mensaje) {
    campo.classList.add("invalido");
    let aviso = campo.closest(".campo").querySelector(".error-campo");
    if (!aviso) {
      aviso = document.createElement("small");
      aviso.className = "error-campo";
      campo.closest(".campo").appendChild(aviso);
    }
    aviso.textContent = mensaje;
  }

  function limpiarErrores(form) {
    form.querySelectorAll(".invalido").forEach(function (c) { c.classList.remove("invalido"); });
    form.querySelectorAll(".error-campo").forEach(function (e) { e.remove(); });
  }

  function mensajeObligatorio(campo, form) {
    if (campo.type === "password") return "La contraseña es obligatoria.";
    const etiqueta = form.querySelector('label[for="' + campo.id + '"]');
    const nombre = etiqueta ? etiqueta.textContent.trim().toLowerCase() : "campo";
    return "El " + nombre + " es obligatorio.";
  }

  document.querySelectorAll("form[data-validar]").forEach(function (form) {
    form.addEventListener("submit", function (evento) {
      limpiarErrores(form);
      let valido = true;
      const campos = form.querySelectorAll("input[required]");
      campos.forEach(function (campo) {
        if (campo.type === "checkbox") return;
        if (!campo.value.trim()) {
          marcarError(campo, mensajeObligatorio(campo, form));
          valido = false;
        }
      });

      const usuario = form.querySelector('input[name="usuario"]');
      const nueva = form.querySelector('input[name="password"][data-medidor], input[name="password_nueva"]');
      const confirmacion = form.querySelector('input[name="confirmar_password"]');
      if (nueva && nueva.value) {
        if (nueva.value.length < MIN_PASSWORD) {
          marcarError(nueva, "La contraseña debe tener al menos " + MIN_PASSWORD + " caracteres.");
          valido = false;
        } else if (usuario && usuario.value && nueva.value.trim().toLowerCase() === usuario.value.trim().toLowerCase()) {
          marcarError(nueva, "La contraseña no puede ser igual al usuario.");
          valido = false;
        }
        if (confirmacion && confirmacion.value && confirmacion.value !== nueva.value) {
          marcarError(confirmacion, "Las contraseñas no coinciden.");
          valido = false;
        }
      }
      if (!valido) {
        evento.preventDefault();
        const primero = form.querySelector(".invalido");
        if (primero) primero.focus();
      }
    });
  });

  document.querySelectorAll("form[data-confirmar]").forEach(function (form) {
    form.addEventListener("submit", function (evento) {
      if (!window.confirm(form.dataset.confirmar)) evento.preventDefault();
    });
  });

  /* ---------------------------------------------------------------------
   * Código de recuperación: formato, copiar, guardar e imprimir
   * ------------------------------------------------------------------- */
  document.querySelectorAll("[data-formato-codigo]").forEach(function (campo) {
    campo.addEventListener("input", function () {
      const limpio = campo.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 16);
      campo.value = (limpio.match(/.{1,4}/g) || []).join("-");
    });
  });

  const contenedorCodigo = document.getElementById("codigo-recuperacion");
  if (contenedorCodigo) {
    const codigo = contenedorCodigo.dataset.codigo;
    const copiar = document.querySelector("[data-copiar-codigo]");
    const descargar = document.querySelector("[data-descargar-codigo]");
    const imprimir = document.querySelector("[data-imprimir-codigo]");
    const casilla = document.getElementById("confirmo-codigo");
    const continuar = document.getElementById("boton-continuar");

    if (copiar) {
      copiar.addEventListener("click", function () {
        const original = copiar.innerHTML;
        const listo = function () {
          copiar.textContent = "Copiado";
          setTimeout(function () { copiar.innerHTML = original; }, 1800);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(codigo).then(listo, function () { seleccionarCodigo(); });
        } else {
          seleccionarCodigo();
        }
      });
    }
    function seleccionarCodigo() {
      const nodo = contenedorCodigo.querySelector(".codigo");
      const rango = document.createRange();
      rango.selectNodeContents(nodo);
      const seleccion = window.getSelection();
      seleccion.removeAllRanges();
      seleccion.addRange(rango);
    }
    if (descargar) {
      descargar.addEventListener("click", function () {
        const contenido =
          "Mis Finanzas - Código de recuperación\r\n" +
          "=====================================\r\n\r\n" +
          codigo + "\r\n\r\n" +
          "Este código permite restablecer la contraseña de la aplicación local.\r\n" +
          "Sólo puede utilizarse una vez. Guárdalo en un lugar seguro.\r\n" +
          "Generado: " + new Date().toLocaleString("es-MX") + "\r\n";
        const blob = new Blob([contenido], { type: "text/plain;charset=utf-8" });
        const enlace = document.createElement("a");
        enlace.href = URL.createObjectURL(blob);
        enlace.download = "mis-finanzas-codigo-recuperacion.txt";
        document.body.appendChild(enlace);
        enlace.click();
        setTimeout(function () { URL.revokeObjectURL(enlace.href); enlace.remove(); }, 500);
      });
    }
    if (imprimir) imprimir.addEventListener("click", function () { window.print(); });
    if (casilla && continuar) {
      casilla.addEventListener("change", function () { continuar.disabled = !casilla.checked; });
    }
  }

  /* ---------------------------------------------------------------------
   * Diálogos sencillos
   * ------------------------------------------------------------------- */
  document.querySelectorAll("[data-abrir]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      const dialogo = document.getElementById(boton.dataset.abrir);
      if (!dialogo) return;
      dialogo.hidden = false;
      const primero = dialogo.querySelector("input");
      if (primero) primero.focus();
    });
  });
  document.querySelectorAll(".modal [data-cerrar]").forEach(function (boton) {
    boton.addEventListener("click", function () { boton.closest(".modal").hidden = true; });
  });
  document.querySelectorAll(".modal").forEach(function (modal) {
    modal.addEventListener("click", function (e) { if (e.target === modal && modal.id !== "aviso-inactividad") modal.hidden = true; });
  });

  /* ---------------------------------------------------------------------
   * Bloqueo automático por inactividad
   * ------------------------------------------------------------------- */
  const cuerpo = document.body;
  const aviso = document.getElementById("aviso-inactividad");
  if (cuerpo.classList.contains("pagina-app") && aviso) {
    const minutos = parseInt(cuerpo.dataset.inactividadMinutos, 10) || 30;
    const avisoSegundos = parseInt(cuerpo.dataset.avisoSegundos, 10) || 60;
    const totalMs = minutos * 60 * 1000;
    const avisoMs = Math.max(totalMs - avisoSegundos * 1000, 1000);
    const contador = document.getElementById("aviso-segundos");
    const formBloqueo = document.getElementById("form-bloqueo-auto");
    let temporizadorAviso = null;
    let temporizadorBloqueo = null;
    let intervalo = null;
    let avisando = false;

    function bloquearAhora() {
      if (formBloqueo) formBloqueo.submit();
    }

    function mostrarAviso() {
      avisando = true;
      aviso.hidden = false;
      let restante = avisoSegundos;
      if (contador) contador.textContent = String(restante);
      intervalo = setInterval(function () {
        restante -= 1;
        if (contador) contador.textContent = String(Math.max(restante, 0));
        if (restante <= 0) clearInterval(intervalo);
      }, 1000);
      temporizadorBloqueo = setTimeout(bloquearAhora, avisoSegundos * 1000);
    }

    function reiniciar() {
      if (avisando) return; // durante el aviso sólo cuenta el botón "Continuar sesión"
      clearTimeout(temporizadorAviso);
      temporizadorAviso = setTimeout(mostrarAviso, avisoMs);
    }

    function continuar() {
      avisando = false;
      aviso.hidden = true;
      clearInterval(intervalo);
      clearTimeout(temporizadorBloqueo);
      reiniciar();
      // Renovar la marca de actividad en el servidor.
      fetch(window.location.pathname, { method: "GET", credentials: "same-origin", cache: "no-store" }).catch(function () {});
    }

    ["mousemove", "mousedown", "keydown", "scroll", "touchstart"].forEach(function (evento) {
      document.addEventListener(evento, reiniciar, { passive: true });
    });
    const botonContinuar = aviso.querySelector("[data-continuar-sesion]");
    if (botonContinuar) botonContinuar.addEventListener("click", continuar);
    reiniciar();
  }

  /* ---------------------------------------------------------------------
   * Evitar que el botón "Atrás" muestre páginas privadas desde la caché
   * ------------------------------------------------------------------- */
  window.addEventListener("pageshow", function (evento) {
    if (evento.persisted && cuerpo.classList.contains("pagina-app")) {
      window.location.reload();
    }
  });
})();
