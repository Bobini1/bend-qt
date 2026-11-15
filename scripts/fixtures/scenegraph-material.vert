#version 440
layout(location = 0) in vec4 vertex;
layout(std140, binding = 0) uniform buf {
    mat4 matrix;
    float opacity;
    vec4 tint;
    vec4 transparentColor;
    float colorKeyEnabled;
    float blendMode;
} uniforms;
void main() { gl_Position = uniforms.matrix * vertex; }
