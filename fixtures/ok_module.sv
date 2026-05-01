// fixtures/ok_module.sv — minimal valid module for analyze smoke tests.
module ok_module (
    input  logic i_clk,
    input  logic i_rst_n,
    output logic o_done
);
    assign o_done = 1'b0;
endmodule
