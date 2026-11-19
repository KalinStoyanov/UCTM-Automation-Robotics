# DD-M2 — Authorship, third-party software and use restrictions

**Project:** DD-M2 / Unitree Go2 Air  
**Institution:** University of Chemical Technology and Metallurgy (UCTM), Sofia, Bulgaria  
**Team:** Department of Automation — faculty members and students  
**Document version:** 1.0 (2026-11-19)

## Project code

The DD-M2 team developed the integration, application logic, operator
interface, control workflows and AI integration described in this repository.
The team's original code in the `Go2/` directory is governed by
[`LICENSE`](LICENSE): **restricted, non-commercial educational and
research use**. Commercial use and redistribution require prior written
authorization from the relevant rights holder(s).

**Public GitHub access does not mean unrestricted open-source licensing.**
The project code is **source-available**, not OSI-approved open source.

## External components

The repository integrates independent third-party technologies. Their
licenses, copyright notices, model terms and distribution conditions apply
separately and take precedence for their respective components.

| Component | Developer / origin | Version / identification | Licensing note |
| --- | --- | --- | --- |
| MediaPipe Gesture Recognizer | Google | Python package `mediapipe==1.2.3`; `gesture_recognizer.task` model file | MediaPipe framework: Apache-2.0; verify the model asset's own terms and exact version separately |
| YOLO11n | Ultralytics | `yolo11n.pt`; Python package `ultralytics==8.4.215` | Ultralytics offers AGPL-3.0 and Enterprise licensing; review obligations for the actual deployment/distribution |
| Unitree Go2 Air | Unitree Robotics | Robot firmware 1.1.12 | Robot firmware and proprietary interfaces are not relicensed by this project |
| WebRTC client | Independent library maintainers | `unitree_webrtc_connect==2.2.0` | Consult the dependency's distributed license |
| Flask / Flask-SocketIO | Their respective maintainers | `Flask==3.1.3`, `Flask-SocketIO==5.7.2` | Consult their respective licenses |
| OpenCV | OpenCV contributors | `opencv-python==5.1.0.95` | Consult the package and upstream licenses |

The version numbers above identify dependencies pinned in
`Go2/go2_control/requirements-go2-control.txt` for the v0.26.0 release.
They do not independently establish the version of every pretrained model.

## Important license boundary

The project's restricted-use license applies only to material for which
the project rights holder(s) can grant permission. It does not replace,
restrict, or override any rights granted by a third-party open-source
license. In particular, distributing a combined work may require
additional review of Ultralytics AGPL-3.0 obligations.

## Safety

Robot motion can cause injury or damage. Operate only with appropriate
supervision, an unobstructed test area and functional stop controls.
See the operator documentation for safe use.

## Additional permissions

For commercial use, redistribution, or special permission, contact the
repository maintainers. Written authorization must come from the
appropriate rights holder(s).
