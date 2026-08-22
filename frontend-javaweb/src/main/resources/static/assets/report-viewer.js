(function () {
    "use strict";

    const VERTEX_SHADER = `
        attribute vec3 a_position;
        attribute vec3 a_normal;
        uniform mat4 u_mvp;
        uniform mat4 u_model;
        varying vec3 v_normal;
        varying vec3 v_position;
        void main() {
            vec4 world = u_model * vec4(a_position, 1.0);
            v_position = world.xyz;
            v_normal = mat3(u_model) * a_normal;
            gl_Position = u_mvp * vec4(a_position, 1.0);
        }
    `;

    const FRAGMENT_SHADER = `
        precision mediump float;
        uniform vec4 u_color;
        varying vec3 v_normal;
        varying vec3 v_position;
        void main() {
            vec3 normal = normalize(v_normal);
            vec3 lightA = normalize(vec3(0.4, 0.8, 0.7));
            vec3 lightB = normalize(vec3(-0.8, 0.3, -0.4));
            float diffuse = max(dot(normal, lightA), 0.0) * 0.68 + max(dot(normal, lightB), 0.0) * 0.24;
            float rim = pow(1.0 - abs(normal.z), 2.0) * 0.18;
            vec3 color = u_color.rgb * (0.38 + diffuse + rim);
            gl_FragColor = vec4(color, u_color.a);
        }
    `;

    function createShader(gl, type, source) {
        const shader = gl.createShader(type);
        if (!shader) {
            throw new Error("WebGL shader 创建失败，请确认浏览器已启用 WebGL");
        }
        gl.shaderSource(shader, source);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
            throw new Error(gl.getShaderInfoLog(shader) || "WebGL shader 编译失败");
        }
        return shader;
    }

    function createProgram(gl) {
        const program = gl.createProgram();
        if (!program) {
            throw new Error("WebGL program 创建失败，请确认浏览器已启用 WebGL");
        }
        gl.attachShader(program, createShader(gl, 35633, VERTEX_SHADER));
        gl.attachShader(program, createShader(gl, 35632, FRAGMENT_SHADER));
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
            throw new Error(gl.getProgramInfoLog(program) || "WebGL program 创建失败");
        }
        return program;
    }

    function identity() {
        return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
    }

    function multiply(a, b) {
        const out = new Array(16).fill(0);
        for (let row = 0; row < 4; row += 1) {
            for (let col = 0; col < 4; col += 1) {
                for (let k = 0; k < 4; k += 1) {
                    out[col * 4 + row] += a[k * 4 + row] * b[col * 4 + k];
                }
            }
        }
        return out;
    }

    function perspective(fov, aspect, near, far) {
        const f = 1 / Math.tan(fov / 2);
        const nf = 1 / (near - far);
        return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0];
    }

    function lookAt(eye, center, up) {
        const z = normalize(sub(eye, center));
        const x = normalize(cross(up, z));
        const y = cross(z, x);
        return [
            x[0], y[0], z[0], 0,
            x[1], y[1], z[1], 0,
            x[2], y[2], z[2], 0,
            -dot(x, eye), -dot(y, eye), -dot(z, eye), 1
        ];
    }

    function sub(a, b) {
        return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
    }

    function cross(a, b) {
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    }

    function dot(a, b) {
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    }

    function normalize(v) {
        const len = Math.hypot(v[0], v[1], v[2]) || 1;
        return [v[0] / len, v[1] / len, v[2] / len];
    }

    function readGlb(buffer) {
        const view = new DataView(buffer);
        if (view.getUint32(0, true) !== 0x46546c67) {
            throw new Error("三维模型不是有效 GLB 文件");
        }
        let offset = 12;
        let json = null;
        let bin = null;
        while (offset < buffer.byteLength) {
            const length = view.getUint32(offset, true);
            const type = view.getUint32(offset + 4, true);
            const chunk = buffer.slice(offset + 8, offset + 8 + length);
            if (type === 0x4e4f534a) {
                json = JSON.parse(new TextDecoder("utf-8").decode(chunk));
            } else if (type === 0x004e4942) {
                bin = chunk;
            }
            offset += 8 + length;
        }
        if (!json || !bin) {
            throw new Error("GLB 缺少 JSON 或 BIN 数据块");
        }
        return { json, bin };
    }

    function componentArray(componentType) {
        if (componentType === 5126) return Float32Array;
        if (componentType === 5125) return Uint32Array;
        if (componentType === 5123) return Uint16Array;
        if (componentType === 5121) return Uint8Array;
        throw new Error(`不支持的 GLB componentType：${componentType}`);
    }

    function typeSize(type) {
        return { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 }[type] || 1;
    }

    function accessorData(asset, index) {
        const accessor = asset.json.accessors[index];
        const view = asset.json.bufferViews[accessor.bufferView];
        const ArrayType = componentArray(accessor.componentType);
        const byteOffset = (view.byteOffset || 0) + (accessor.byteOffset || 0);
        const itemSize = typeSize(accessor.type);
        const count = accessor.count * itemSize;
        return new ArrayType(asset.bin, byteOffset, count);
    }

    function materialColor(asset, index) {
        const material = asset.json.materials?.[index] || {};
        const color = material.pbrMetallicRoughness?.baseColorFactor || [0.28, 0.52, 0.92, 0.72];
        return [color[0], color[1], color[2], Math.max(0.36, color[3] ?? 0.72)];
    }

    function itkColor(index, fallback) {
        const palette = [
            [0.90, 0.06, 0.06, 0.82],
            [0.10, 0.80, 0.18, 0.78],
            [0.08, 0.32, 0.96, 0.80],
            [0.96, 0.86, 0.08, 0.78],
            [0.82, 0.10, 0.92, 0.80],
            [0.04, 0.82, 0.92, 0.78],
            [0.96, 0.48, 0.06, 0.80],
            [0.62, 0.38, 0.98, 0.78],
            [0.96, 0.20, 0.54, 0.80],
            [0.28, 0.92, 0.62, 0.78],
            [0.72, 0.76, 0.82, 0.72],
            [0.58, 0.86, 0.16, 0.78]
        ];
        const color = fallback || palette[index % palette.length];
        return [color[0], color[1], color[2], Math.max(0.58, color[3] ?? 0.76)];
    }

    function colorCss(color) {
        return `rgb(${Math.round(color[0] * 255)}, ${Math.round(color[1] * 255)}, ${Math.round(color[2] * 255)})`;
    }

    function displayName(name) {
        const raw = String(name || "").split(":").pop();
        const names = {
            spleen: "脾脏",
            kidney_right: "右肾",
            kidney_left: "左肾",
            liver: "肝脏",
            stomach: "胃",
            pancreas: "胰腺",
            adrenal_gland_right: "右肾上腺",
            adrenal_gland_left: "左肾上腺",
            aorta: "主动脉",
            inferior_vena_cava: "下腔静脉",
            portal_vein_and_splenic_vein: "门静脉/脾静脉",
            duodenum: "十二指肠",
            small_bowel: "小肠",
            colon: "结肠"
        };
        return names[raw] || raw.replaceAll("_", " ");
    }

    class ReportViewer {
        constructor(container) {
            if (!container) throw new Error("三维容器不存在");
            this.container = container;
            this.shell = document.createElement("div");
            this.shell.className = "report-3d-layout";
            this.controlsPanel = document.createElement("div");
            this.controlsPanel.className = "report-3d-controls";
            this.stage = document.createElement("div");
            this.stage.className = "report-3d-stage";
            this.canvas = document.createElement("canvas");
            this.container.innerHTML = "";
            this.stage.appendChild(this.canvas);
            this.shell.appendChild(this.controlsPanel);
            this.shell.appendChild(this.stage);
            this.container.appendChild(this.shell);
            this.gl = null;
            this.ctx2d = null;
            this.program = null;
            this.renderMode = "webgl";
            try {
                this.gl = this.canvas.getContext("webgl2", { antialias: true, alpha: true })
                    || this.canvas.getContext("webgl", { antialias: true, alpha: true })
                    || this.canvas.getContext("experimental-webgl", { antialias: true, alpha: true });
                if (!this.gl) throw new Error("当前浏览器不支持 WebGL");
                this.uintIndexExtension = this.gl.getExtension("OES_element_index_uint");
                this.program = createProgram(this.gl);
            } catch (error) {
                this.gl = null;
                this.program = null;
                this.renderMode = "canvas";
                this.ctx2d = this.canvas.getContext("2d");
                if (!this.ctx2d) {
                    throw error;
                }
            }
            this.meshes = [];
            this.manifestMeshes = [];
            this.center = [0, 0, 0];
            this.radius = 160;
            this.yaw = 0.8;
            this.pitch = 0.45;
            this.distance = 360;
            this.dragging = false;
            this.lastPointer = [0, 0];
            this.animationId = null;
            this.resizeObserver = new ResizeObserver(() => this.resize());
            this.resizeObserver.observe(this.stage);
            this.bindEvents();
            this.resize();
            this.animate();
        }

        async load(meshUrl, manifestUrl) {
            let manifest = null;
            if (manifestUrl) {
                const manifestResponse = await fetch(manifestUrl, { cache: "no-store" });
                if (!manifestResponse.ok) throw new Error(`三维模型清单加载失败：HTTP ${manifestResponse.status}`);
                manifest = await manifestResponse.json();
            }
            const response = await fetch(meshUrl, { cache: "no-store" });
            if (!response.ok) throw new Error(`三维模型加载失败：HTTP ${response.status}`);
            const asset = readGlb(await response.arrayBuffer());
            this.manifestMeshes = Array.isArray(manifest?.meshes) ? manifest.meshes : [];
            this.uploadMeshes(asset);
            this.renderControls();
            this.fitCamera();
            return { renderMode: this.renderMode };
        }

        uploadMeshes(asset) {
            const gl = this.gl;
            this.disposeMeshes();
            const mins = [Infinity, Infinity, Infinity];
            const maxs = [-Infinity, -Infinity, -Infinity];
            let meshIndex = 0;
            for (const mesh of asset.json.meshes || []) {
                for (const primitive of mesh.primitives || []) {
                    const manifestMesh = this.manifestMeshes[meshIndex] || {};
                    const meshName = manifestMesh.name || mesh.name || `结构 ${meshIndex + 1}`;
                    const positions = accessorData(asset, primitive.attributes.POSITION);
                    const normals = primitive.attributes.NORMAL == null
                        ? new Float32Array(positions.length)
                        : accessorData(asset, primitive.attributes.NORMAL);
                    const indices = accessorData(asset, primitive.indices);
                    for (let i = 0; i < positions.length; i += 3) {
                        mins[0] = Math.min(mins[0], positions[i]);
                        mins[1] = Math.min(mins[1], positions[i + 1]);
                        mins[2] = Math.min(mins[2], positions[i + 2]);
                        maxs[0] = Math.max(maxs[0], positions[i]);
                        maxs[1] = Math.max(maxs[1], positions[i + 1]);
                        maxs[2] = Math.max(maxs[2], positions[i + 2]);
                    }
                    const meshRecord = {
                        id: meshIndex,
                        name: meshName,
                        visible: manifestMesh.visible_by_default !== false,
                        positions,
                        indices,
                        color: itkColor(meshIndex, manifestMesh.color || materialColor(asset, primitive.material))
                    };
                    if (gl) {
                        const positionBuffer = gl.createBuffer();
                        gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
                        gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
                        const normalBuffer = gl.createBuffer();
                        gl.bindBuffer(gl.ARRAY_BUFFER, normalBuffer);
                        gl.bufferData(gl.ARRAY_BUFFER, normals, gl.STATIC_DRAW);
                        const indexBuffer = gl.createBuffer();
                        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
                        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);
                        meshRecord.positionBuffer = positionBuffer;
                        meshRecord.normalBuffer = normalBuffer;
                        meshRecord.indexBuffer = indexBuffer;
                        meshRecord.indexCount = indices.length;
                        meshRecord.indexType = this.indexType(indices);
                    }
                    this.meshes.push(meshRecord);
                    meshIndex += 1;
                }
            }
            if (!this.meshes.length) throw new Error("三维模型中没有可渲染网格");
            this.center = [(mins[0] + maxs[0]) / 2, (mins[1] + maxs[1]) / 2, (mins[2] + maxs[2]) / 2];
            this.radius = Math.max(maxs[0] - mins[0], maxs[1] - mins[1], maxs[2] - mins[2], 1) / 2;
        }

        indexType(indices) {
            if (indices instanceof Uint32Array) {
                if (!this.uintIndexExtension) {
                    throw new Error("当前浏览器 WebGL 不支持 Uint32 三维模型索引");
                }
                return this.gl.UNSIGNED_INT;
            }
            return indices instanceof Uint8Array ? this.gl.UNSIGNED_BYTE : this.gl.UNSIGNED_SHORT;
        }

        fitCamera() {
            this.distance = this.radius * 4.2;
        }

        renderControls() {
            this.controlsPanel.innerHTML = "";
            const title = document.createElement("div");
            title.className = "report-3d-controls-title";
            title.textContent = "结构显示";
            this.controlsPanel.appendChild(title);

            const buttons = document.createElement("div");
            buttons.className = "report-3d-control-actions";
            const showAll = document.createElement("button");
            showAll.type = "button";
            showAll.textContent = "全显";
            showAll.addEventListener("click", () => this.setAllVisible(true));
            const hideAll = document.createElement("button");
            hideAll.type = "button";
            hideAll.textContent = "全隐";
            hideAll.addEventListener("click", () => this.setAllVisible(false));
            buttons.appendChild(showAll);
            buttons.appendChild(hideAll);
            this.controlsPanel.appendChild(buttons);

            const list = document.createElement("div");
            list.className = "report-3d-control-list";
            for (const mesh of this.meshes) {
                const label = document.createElement("label");
                label.className = "report-3d-control-row";
                const input = document.createElement("input");
                input.type = "checkbox";
                input.checked = mesh.visible;
                input.addEventListener("change", () => {
                    mesh.visible = input.checked;
                });
                const swatch = document.createElement("span");
                swatch.className = "report-3d-swatch";
                swatch.style.backgroundColor = colorCss(mesh.color);
                const text = document.createElement("span");
                text.textContent = displayName(mesh.name);
                label.appendChild(input);
                label.appendChild(swatch);
                label.appendChild(text);
                list.appendChild(label);
            }
            this.controlsPanel.appendChild(list);
        }

        setAllVisible(visible) {
            for (const mesh of this.meshes) {
                mesh.visible = visible;
            }
            for (const input of this.controlsPanel.querySelectorAll("input[type='checkbox']")) {
                input.checked = visible;
            }
        }

        bindEvents() {
            this.canvas.addEventListener("pointerdown", (event) => {
                this.dragging = true;
                this.lastPointer = [event.clientX, event.clientY];
                this.canvas.setPointerCapture(event.pointerId);
            });
            this.canvas.addEventListener("pointermove", (event) => {
                if (!this.dragging) return;
                const dx = event.clientX - this.lastPointer[0];
                const dy = event.clientY - this.lastPointer[1];
                this.lastPointer = [event.clientX, event.clientY];
                this.yaw -= dx * 0.008;
                this.pitch = Math.max(-1.2, Math.min(1.2, this.pitch + dy * 0.008));
            });
            this.canvas.addEventListener("pointerup", () => {
                this.dragging = false;
            });
            this.canvas.addEventListener("wheel", (event) => {
                event.preventDefault();
                this.distance = Math.max(this.radius * 1.2, Math.min(this.radius * 12, this.distance * (event.deltaY > 0 ? 1.12 : 0.88)));
            }, { passive: false });
        }

        resize() {
            const width = Math.max(1, this.stage.clientWidth);
            const height = Math.max(1, this.stage.clientHeight);
            const scale = Math.min(window.devicePixelRatio || 1, 2);
            this.canvas.width = Math.round(width * scale);
            this.canvas.height = Math.round(height * scale);
            this.canvas.style.width = `${width}px`;
            this.canvas.style.height = `${height}px`;
            if (this.gl) {
                this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
            }
        }

        draw() {
            if (!this.gl) {
                this.drawCanvas();
                return;
            }
            const gl = this.gl;
            gl.clearColor(0.0, 0.0, 0.0, 1);
            gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
            gl.enable(gl.DEPTH_TEST);
            gl.enable(gl.BLEND);
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
            gl.useProgram(this.program);

            const aspect = this.canvas.width / Math.max(1, this.canvas.height);
            const eye = [
                this.center[0] + Math.cos(this.pitch) * Math.sin(this.yaw) * this.distance,
                this.center[1] + Math.sin(this.pitch) * this.distance,
                this.center[2] + Math.cos(this.pitch) * Math.cos(this.yaw) * this.distance
            ];
            const projection = perspective(Math.PI / 4, aspect, Math.max(0.1, this.radius / 100), this.distance + this.radius * 8);
            const view = lookAt(eye, this.center, [0, 1, 0]);
            const model = identity();
            const mvp = multiply(projection, multiply(view, model));

            const locPosition = gl.getAttribLocation(this.program, "a_position");
            const locNormal = gl.getAttribLocation(this.program, "a_normal");
            gl.uniformMatrix4fv(gl.getUniformLocation(this.program, "u_mvp"), false, new Float32Array(mvp));
            gl.uniformMatrix4fv(gl.getUniformLocation(this.program, "u_model"), false, new Float32Array(model));

            for (const mesh of this.meshes) {
                if (!mesh.visible) continue;
                gl.bindBuffer(gl.ARRAY_BUFFER, mesh.positionBuffer);
                gl.enableVertexAttribArray(locPosition);
                gl.vertexAttribPointer(locPosition, 3, gl.FLOAT, false, 0, 0);
                gl.bindBuffer(gl.ARRAY_BUFFER, mesh.normalBuffer);
                gl.enableVertexAttribArray(locNormal);
                gl.vertexAttribPointer(locNormal, 3, gl.FLOAT, false, 0, 0);
                gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, mesh.indexBuffer);
                gl.uniform4fv(gl.getUniformLocation(this.program, "u_color"), new Float32Array(mesh.color));
                gl.drawElements(gl.TRIANGLES, mesh.indexCount, mesh.indexType, 0);
            }
        }

        drawCanvas() {
            const ctx = this.ctx2d;
            const width = this.canvas.width;
            const height = this.canvas.height;
            ctx.fillStyle = "#000";
            ctx.fillRect(0, 0, width, height);
            if (!this.meshes.length) return;

            const cosY = Math.cos(this.yaw);
            const sinY = Math.sin(this.yaw);
            const cosP = Math.cos(this.pitch);
            const sinP = Math.sin(this.pitch);
            const scale = Math.min(width, height) / Math.max(1, this.radius * 2.8);

            for (const mesh of this.meshes) {
                if (!mesh.visible) continue;
                const color = mesh.color;
                ctx.fillStyle = `rgba(${Math.round(color[0] * 255)}, ${Math.round(color[1] * 255)}, ${Math.round(color[2] * 255)}, ${Math.min(1, Math.max(0.55, color[3]))})`;
                const positions = mesh.positions;
                const vertexCount = positions.length / 3;
                const step = Math.max(1, Math.floor(vertexCount / 6500));
                for (let i = 0; i < positions.length; i += 3 * step) {
                    const x = positions[i] - this.center[0];
                    const y = positions[i + 1] - this.center[1];
                    const z = positions[i + 2] - this.center[2];
                    const x1 = x * cosY - z * sinY;
                    const z1 = x * sinY + z * cosY;
                    const y1 = y * cosP - z1 * sinP;
                    const z2 = y * sinP + z1 * cosP;
                    const perspectiveFactor = this.distance / Math.max(1, this.distance + z2);
                    const sx = width / 2 + x1 * scale * perspectiveFactor;
                    const sy = height / 2 - y1 * scale * perspectiveFactor;
                    ctx.fillRect(sx, sy, 2, 2);
                }
            }
        }

        animate() {
            this.animationId = window.requestAnimationFrame(() => this.animate());
            this.draw();
        }

        disposeMeshes() {
            const gl = this.gl;
            for (const mesh of this.meshes) {
                if (gl && mesh.positionBuffer) gl.deleteBuffer(mesh.positionBuffer);
                if (gl && mesh.normalBuffer) gl.deleteBuffer(mesh.normalBuffer);
                if (gl && mesh.indexBuffer) gl.deleteBuffer(mesh.indexBuffer);
            }
            this.meshes = [];
        }

        dispose() {
            if (this.animationId) window.cancelAnimationFrame(this.animationId);
            this.resizeObserver?.disconnect();
            this.disposeMeshes();
            this.container.innerHTML = "";
        }
    }

    window.createReportViewer = function (container) {
        return new ReportViewer(container);
    };
})();
