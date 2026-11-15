#version 440
layout(location = 0) out vec4 color;
layout(std140, binding = 0) uniform buf {
    mat4 matrix;
    float opacity;
    vec4 tint;
    vec4 transparentColor;
    float colorKeyEnabled;
    float blendMode;
} uniforms;
void main() {
    vec3 rgb = uniforms.tint.rgb;
    if (uniforms.colorKeyEnabled > 0.5) rgb = uniforms.transparentColor.rgb;
    color = vec4(rgb * uniforms.opacity, uniforms.blendMode);
}
