# Requisitos del Sistema de Gestión de Monitores

---

## 1. Requisitos Funcionales (RF)

### Módulo de Gestión de Usuarios

#### RF-01 | Registro Integral y Unicidad de Usuarios

**Descripción Detallada:**
El sistema debe proveer la capacidad de almacenar los datos de identificación de todas las personas que interactúen con la plataforma. La base de datos debe impedir la duplicidad de registros basada en el documento de identidad.

- **Actores:** Administrador.
- **Precondiciones:** El usuario a registrar no debe existir previamente en el sistema.

**Reglas de Negocio y Datos:**
- El campo `nombre_completo` es de carácter obligatorio (`NOT NULL`) y debe soportar hasta 100 caracteres.
- El campo `numero_cedula` es obligatorio, debe ser estrictamente numérico/alfanumérico y único a nivel de toda la base de datos (`UNIQUE CONSTRAINT`) y `PK`.

**Criterios de Aceptación:**
Si se intenta registrar a un usuario con una cédula ya existente, el sistema (a nivel de base de datos) debe rechazar la transacción y arrojar un error de duplicidad.

---

#### RF-02 | Asignación y Gestión Estricta de Roles

**Descripción Detallada:**
El sistema debe categorizar a cada usuario registrado bajo un nivel de acceso o perfil funcional específico. Esto determinará su capacidad de interacción (ya sea administrar o ser el monitor de una sala).

- **Actores:** Administrador.

**Reglas de Negocio y Datos:**
- Solo existirán dos roles permitidos por el dominio del negocio: `Administrador` y `Monitor`.
- Un usuario debe tener asignado al menos un rol obligatoriamente al momento de su creación.

**Criterios de Aceptación:**
La base de datos debe contar con un catálogo de roles o una restricción (`CHECK`/`ENUM`) que impida insertar un rol distinto a los mencionados (ej. no se puede insertar el rol `"Docente"` porque el alcance del sistema no lo contempla para la gestión).

---

### Módulo de Gestión de Espacios (Salas)

#### RF-03 | Inventario Físico de Salas de Cómputo

**Descripción Detallada:**
El sistema debe mantener un catálogo maestro con la información de los espacios físicos (salas de cómputo) que la institución tiene habilitados para la asignación de turnos.

**Reglas de Negocio y Datos:**
- Cada sala debe tener un `codigo_sala` alfanumérico que la identifique unívocamente (ej: `"SALA-101"`, `"LAB-REDES"`).
- Este código no puede repetirse bajo ninguna circunstancia (`UNIQUE CONSTRAINT`).

**Criterios de Aceptación:**
Se debe poder registrar, consultar y actualizar el nombre o código de la sala sin afectar el historial de préstamos o asignaciones pasadas.

---

### Módulo de Horarios y Asignaciones

#### RF-04 | Parametrización de Bloques Horarios

**Descripción Detallada:**
El sistema debe permitir la creación de la malla de horarios de la institución. En lugar de texto libre, los horarios deben tratarse como bloques de tiempo estructurados para permitir cruces de disponibilidad.

**Reglas de Negocio y Datos:**
- Un horario se compone de un `dia_semana` (Lunes a Sábado/Domingo), una `hora_inicio` y una `hora_fin`.
- Los formatos de hora deben almacenarse en estándar de 24 horas (ej: `14:00:00`).

**Criterios de Aceptación:**
Se deben poder crear múltiples franjas horarias estandarizadas (ej. Lunes de `08:00` a `10:00`) que luego estarán disponibles para asignarse a cualquier sala.

---

#### RF-05 | Asignación Transaccional de Turnos (Monitor-Sala-Horario)

**Descripción Detallada:**
El núcleo operativo del sistema. Consiste en la vinculación formal donde se dictamina que un (1) Monitor específico es responsable de una (1) Sala específica durante un (1) Horario específico.

- **Precondiciones:** El usuario asignado debe tener el rol de Monitor. La sala y el horario deben existir previamente.

**Reglas de Negocio (Prevención de Conflictos):**
- **Regla 1:** Una misma sala, en un mismo horario, **NO** puede tener asignados a dos monitores distintos. *(Evitar sobreasignación de salas).*
- **Regla 2:** Un mismo monitor **NO** puede estar asignado a dos salas diferentes en el mismo horario. *(Evitar ubicuidad del monitor).*

**Criterios de Aceptación:**
La base de datos debe tener claves únicas compuestas (*Composite Unique Keys*) que hagan explotar la transacción si el Administrador intenta generar un choque de horarios.

---

### Módulo de Cambios y Novedades

#### RF-06 y RF-07 | Registro Transaccional de Solicitud de Cambio de Turno

**Descripción Detallada:**
Mecanismo mediante el cual un Monitor (Solicitante) indica que no podrá asistir a su turno previamente asignado y propone a otro Monitor (Reemplazo) para que cubra dicho espacio temporal.

- **Actores Involucrados:** Monitor Solicitante, Monitor de Reemplazo.

**Reglas de Negocio y Datos:**
La solicitud debe vincular obligatoriamente cuatro elementos:
1. El turno original afectado (vinculado mediante ID).
2. El usuario que pide el cambio (Monitor Solicitante).
3. El usuario que va a cubrir el turno (Monitor Reemplazo).
4. Fecha y hora en la que se genera la solicitud en el sistema (*Timestamp*).

> El sistema debe impedir lógicamente que el Monitor Solicitante y el Monitor Reemplazo sean la misma persona.

**Criterios de Aceptación:**
Al insertar un cambio de turno, se debe exigir la firma (IDs) de ambos monitores y la referencia exacta del turno (sala y hora) que se está negociando.

---

#### RF-08 | Trazabilidad, Auditoría y Estados del Cambio

**Descripción Detallada:**
El sistema no puede simplemente borrar el turno anterior y crear uno nuevo; debe mantener un historial inmutable para que el Administrador sepa cuándo, quién y por qué se alteró la malla de turnos original.

**Reglas de Negocio:**
- Toda solicitud de cambio debe nacer con un estado por defecto, por ejemplo: `"Registrada"` o `"Pendiente"`.
- Las solicitudes son registros históricos.

**Criterios de Aceptación:**
El administrador debe ser capaz de consultar la tabla de solicitudes y ver un historial completo de todas las novedades ocurridas durante el semestre, ordenadas por fecha de solicitud.

---

## 2. Requisitos No Funcionales (RNF)

### Arquitectura y Restricciones Físicas de la Base de Datos

#### RNF-01 | Paradigma Estricto de Base de Datos Relacional (RDBMS)

- **Especificación Técnica:** El sistema no utilizará esquemas NoSQL (como MongoDB). Se exige un modelo estructurado basado en la **Tercera Forma Normal (3FN)**.
- **Métrica de Cumplimiento:** Todas las entidades deben tener una Clave Primaria (`PK`) atómica. No deben existir atributos multivaluados (ej. guardar dos teléfonos en un mismo campo) ni redundancia de datos (ej. el nombre del monitor no se escribe en la tabla de asignaciones, solo se referencia su ID).

---

#### RNF-02 | Motor de Base de Datos MySQL e InnoDB

- **Especificación Técnica:** El proyecto debe construirse exclusivamente utilizando el motor **MySQL**. A nivel interno, todas las tablas deberán ser creadas usando el sub-motor de almacenamiento **InnoDB**.
- **Justificación:** Solo InnoDB garantiza el cumplimiento de las propiedades **ACID** (*Atomicidad, Consistencia, Aislamiento, Durabilidad*) y permite el bloqueo a nivel de fila y el uso de Claves Foráneas reales, vitales para el RF-05 y RF-06.

---

#### RNF-03 | Portabilidad mediante Entorno XAMPP

- **Especificación Técnica:** El sistema debe estar diseñado de forma portable para que funcione de manera *"Plug and Play"* dentro de la suite **XAMPP** (Apache + MariaDB/MySQL + PHP).
- **Métrica de Cumplimiento:** El código SQL generado no debe contener dependencias de servidores en la nube (como AWS RDS) ni configuraciones avanzadas de clusters. Debe poder ejecutarse exitosamente pegando el código en la consola de **phpMyAdmin** de una instalación limpia de XAMPP.

---

### Diseño, Calidad y Mantenimiento del Código SQL

#### RNF-04 | Aplicación de Integridad Referencial Estricta (Restricciones FK)

- **Especificación Técnica:** La base de datos debe ser auto-protegida. Esto significa que las relaciones entre tablas (Foreign Keys) deben dictar cómo se comporta el borrado y la actualización de datos en cascada.
- **Métrica de Cumplimiento:**
  - `ON DELETE RESTRICT`: Si un Administrador intenta eliminar a un Monitor que ya tiene turnos asignados o historial de cambios, la base de datos debe bloquear el `DELETE` para evitar que queden turnos sin responsable (registros huérfanos).
  - `ON UPDATE CASCADE`: Si el ID de una sala o usuario cambia, este cambio debe reflejarse automáticamente en todas las tablas transaccionales.

---

#### RNF-05 | Automatización del Despliegue (Scripts DDL y DML)

- **Especificación Técnica:** La entrega y pase a producción del sistema no se hará mediante creación manual visual (clics). Se exige la entrega de código fuente SQL puro.
- **Métrica de Cumplimiento:**
  - **Script 1 — Estructura:** Un archivo `.sql` que destruya la base de datos si existe (`DROP DATABASE IF EXISTS`), la cree desde cero, y genere todas las tablas en orden jerárquico (primero las que no tienen dependencias, luego las transaccionales).
  - **Script 2 — Población/Semilla:** Un archivo `.sql` independiente que contenga sentencias `INSERT INTO` masivas para insertar al menos:
    - 2 Roles
    - 5 Usuarios (1 admin, 4 monitores)
    - 3 Salas
    - 5 Horarios
    - 2 asignaciones simuladas
    - 1 solicitud de cambio de turno