/* ==========================================================================
   ATHENA 3D FBX ANIMATED CHARACTER AVATAR ENGINE (Three.js + FBXLoader)
   ========================================================================== */

(function (global) {
  'use strict';

  class AthenaAvatarEngine {
    constructor() {
      this.container = null;
      this.scene = null;
      this.camera = null;
      this.renderer = null;
      
      this.state = 'idle';
      this.targetState = 'idle';
      this.currentActiveKey = 'idle';
      
      // FBX Model Registry
      this.models = {
        idle: { url: '/models/idle.fbx', object: null, mixer: null, action: null },
        breathing: { url: '/models/breathing_idle.fbx', object: null, mixer: null, action: null },
        walking: { url: '/models/walking.fbx', object: null, mixer: null, action: null },
        running: { url: '/models/running.fbx', object: null, mixer: null, action: null },
        fallen: { url: '/models/fall.fbx', object: null, mixer: null, action: null }
      };


      // Lighting
      this.dirLight = null;
      this.ambientLight = null;
      this.rimLight = null;

      // Group Rig
      this.rigGroup = null;

      // Animation Controls
      this.clock = new THREE.Clock();
      this.isDragging = false;
      this.previousMousePosition = { x: 0, y: 0 };
      this.autoRotateSpeed = 0; // Auto-rotation disabled per request

      // Bindings
      this.animate = this.animate.bind(this);
      this.onWindowResize = this.onWindowResize.bind(this);
      this.onPointerDown = this.onPointerDown.bind(this);
      this.onPointerMove = this.onPointerMove.bind(this);
      this.onPointerUp = this.onPointerUp.bind(this);
    }

    init(containerId) {
      if (this.renderer) return;

      this.container = typeof containerId === 'string' ? document.getElementById(containerId) : containerId;
      if (!this.container) {
        console.warn('[AthenaAvatar] Container element not found:', containerId);
        return;
      }

      const width = this.container.clientWidth || 320;
      const height = this.container.clientHeight || 210;

      // 1. Scene Setup
      this.scene = new THREE.Scene();

      // 2. Camera Setup (Centered front-facing view)
      this.camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 100);
      this.camera.position.set(0, 0.95, 2.6);
      this.camera.lookAt(0, 0.7, 0);

      // 3. WebGL Renderer
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      this.renderer.setSize(width, height);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      this.renderer.setClearColor(0x000000, 0);
      this.container.appendChild(this.renderer.domElement);

      // 4. Lighting
      this.ambientLight = new THREE.AmbientLight(0xffffff, 1.1);
      this.scene.add(this.ambientLight);

      this.dirLight = new THREE.DirectionalLight(0x00e5ff, 1.4);
      this.dirLight.position.set(2, 4, 3);
      this.scene.add(this.dirLight);

      this.rimLight = new THREE.PointLight(0x00e5ff, 1.6, 6);
      this.rimLight.position.set(-2, 2, -2);
      this.scene.add(this.rimLight);

      // 5. Rig Parent Group (Fixed facing forward)
      this.rigGroup = new THREE.Group();
      this.rigGroup.rotation.set(0, 0, 0);
      this.scene.add(this.rigGroup);

      // 6. Load FBX Models
      this.loadAllFBXModels();

      // 7. Events
      window.addEventListener('resize', this.onWindowResize);

      // 8. Start Loop
      this.clock.start();
      this.animate();
    }

    loadAllFBXModels() {
      if (typeof THREE.FBXLoader === 'undefined') {
        console.error('[AthenaAvatar] THREE.FBXLoader script is missing!');
        return;
      }
      const loader = new THREE.FBXLoader();

      Object.keys(this.models).forEach((key) => {
        const item = this.models[key];
        loader.load(
          item.url,
          (fbx) => {
            // Scale and center model
            fbx.scale.set(0.0085, 0.0085, 0.0085);
            
            // Align vertical position offsets so all models stay in the exact same center spot
            if (key === 'idle' || key === 'breathing') {
              fbx.position.set(0, 0.2, 0); // Center sitting / breathing model height
            } else if (key === 'fallen') {
              fbx.position.set(0, 0.1, 0);
            } else {
              fbx.position.set(0, 0, 0);
            }


            // Lock root translational motion (X and Z position tracks) so character animates in-place
            if (fbx.animations && fbx.animations.length > 0) {
              const clip = fbx.animations[0];
              clip.tracks.forEach((track) => {
                const trackName = track.name.toLowerCase();
                if (trackName.endsWith('.position')) {
                  const values = track.values;
                  // Lock X and Z axes to 0 for in-place motion
                  for (let i = 0; i < values.length; i += 3) {
                    values[i] = 0;     // Lock X translation
                    values[i + 2] = 0; // Lock Z translation
                  }
                }
              });

              const mixer = new THREE.AnimationMixer(fbx);
              const action = mixer.clipAction(clip);

              if (key === 'fallen') {
                action.setLoop(THREE.LoopOnce);
                action.clampWhenFinished = true;
              } else {
                action.setLoop(THREE.LoopRepeat);
              }

              action.play();
              item.mixer = mixer;
              item.action = action;
            }

            // Refine materials
            fbx.traverse((child) => {
              if (child.isMesh) {
                child.castShadow = true;
                child.receiveShadow = true;
                if (child.material) {
                  if (Array.isArray(child.material)) {
                    child.material.forEach(m => { m.transparent = true; m.opacity = 0.98; });
                  } else {
                    child.material.transparent = true;
                    child.material.opacity = 0.98;
                  }
                }
              }
            });

            item.object = fbx;
            fbx.visible = (key === this.currentActiveKey);
            this.rigGroup.add(fbx);

            console.log(`[AthenaAvatar] Successfully loaded FBX model: ${key}`);
          },
          undefined,
          (err) => {
            console.error(`[AthenaAvatar] Error loading FBX model (${key}):`, err);
          }
        );
      });
    }

    setState(newState) {
      if (!this.renderer && typeof document !== 'undefined') {
        const container = document.getElementById('avatar-container');
        if (container) this.init(container);
      }

      if (!newState) return;
      const lower = String(newState).toLowerCase();
      if (lower.includes('fall')) {
        key = 'fallen';
      } else if (lower.includes('run')) {
        key = 'running';
      } else if (lower.includes('walk') || lower.includes('active') || lower.includes('move')) {
        key = 'walking';
      } else if (lower.includes('breath') || lower.includes('rest') || lower.includes('calm') || lower.includes('recover') || lower.includes('idle')) {
        key = 'breathing';
      } else {
        key = 'breathing';
      }


      this.state = key;
      if (key === this.currentActiveKey) return;
      this.currentActiveKey = key;

      // Keep main parent rig locked facing forward
      if (this.rigGroup) {
        this.rigGroup.position.set(0, 0, 0);
        this.rigGroup.rotation.set(0, 0, 0);
      }

      // Toggle model visibility and trigger animation actions in-place
      Object.keys(this.models).forEach((k) => {
        const item = this.models[k];
        if (item.object) {
          if (k === key) {
            item.object.visible = true;
            if (item.action) {
              item.action.reset();
              item.action.play();
            }
          } else {
            item.object.visible = false;
          }
        }
      });

      // Alert lighting on fall state
      if (key === 'fallen') {
        if (this.dirLight) this.dirLight.color.setHex(0xff3333);
        if (this.rimLight) this.rimLight.color.setHex(0xff0000);
      } else {
        if (this.dirLight) this.dirLight.color.setHex(0x00e5ff);
        if (this.rimLight) this.rimLight.color.setHex(0x00e5ff);
      }
    }

    animate() {
      requestAnimationFrame(this.animate);
      const delta = this.clock.getDelta();

      // Update mixer of current active model
      const activeItem = this.models[this.currentActiveKey];
      if (activeItem && activeItem.mixer) {
        activeItem.mixer.update(delta);
      }

      // Model stays fixed facing forward (no auto-rotation)

      if (this.renderer && this.scene && this.camera) {
        this.renderer.render(this.scene, this.camera);
      }
    }

    onPointerDown(e) {}
    onPointerMove(e) {}
    onPointerUp() {}

    onWindowResize() {
      if (!this.container || !this.renderer || !this.camera) return;
      const width = this.container.clientWidth;
      const height = this.container.clientHeight;
      if (width <= 0 || height <= 0) return;
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height);
    }
  }

  // Export instance to global scope
  global.AthenaAvatar = new AthenaAvatarEngine();

  // Auto initialize on load if container exists
  if (typeof window !== 'undefined') {
    const initFn = () => {
      const container = document.getElementById('avatar-container');
      if (container && window.AthenaAvatar) {
        window.AthenaAvatar.init(container);
      }
    };
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
      setTimeout(initFn, 50);
    } else {
      window.addEventListener('DOMContentLoaded', initFn);
    }
  }

})(typeof window !== 'undefined' ? window : this);
